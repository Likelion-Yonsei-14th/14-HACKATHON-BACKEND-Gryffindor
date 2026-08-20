from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.constants import DEMO_USER_ID
from app.domain.enums import ReservationStatus
from app.errors import AppError
from app.models.product import Product
from app.models.trip import HotelStay, Trip, VisitReservation, VisitReservationProduct
from app.repositories.personalization import PersonalizationRepository
from app.repositories.products import ProductRepository
from app.repositories.stores import StoreRepository
from app.repositories.trips import TripRepository


class TripService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._trips = TripRepository(db)
        self._personalization = PersonalizationRepository(db)
        self._products = ProductRepository(db)
        self._stores = StoreRepository(db)

    def create_trip(self, values: dict[str, Any]) -> Trip:
        self._require_user()
        normalized = _normalize_datetime_values(values)
        trip = self._trips.add(Trip(user_id=DEMO_USER_ID, **normalized))
        self._db.commit()
        return trip

    def list_trips(self) -> list[Trip]:
        self._require_user()
        return self._trips.list_trips(DEMO_USER_ID)

    def get_trip(self, trip_id: UUID, *, detail: bool = False) -> Trip:
        self._require_user()
        trip = (
            self._trips.get_detail(DEMO_USER_ID, trip_id)
            if detail
            else self._trips.get(DEMO_USER_ID, trip_id)
        )
        if trip is None:
            raise AppError(404, "TRIP_NOT_FOUND", "Trip was not found.")
        return trip

    def update_trip(self, trip_id: UUID, changes: dict[str, Any]) -> Trip:
        trip = self.get_trip(trip_id)
        normalized = _normalize_datetime_values(changes)
        starts_at = normalized.get("starts_at", trip.starts_at)
        ends_at = normalized.get("ends_at", trip.ends_at)
        if starts_at is not None and ends_at is not None and ends_at < starts_at:
            raise AppError(422, "INVALID_REQUEST", "Trip end time must follow start time.")
        for field_name, value in normalized.items():
            setattr(trip, field_name, value)
        self._db.commit()
        return trip

    def upsert_hotel(self, trip_id: UUID, values: dict[str, Any]) -> HotelStay:
        trip = self.get_trip(trip_id)
        hotel = self._trips.get_hotel(trip.id)
        normalized = _normalize_datetime_values(values)
        if hotel is None:
            hotel = self._trips.add_hotel(HotelStay(trip_id=trip.id, **normalized))
        else:
            for field_name, value in normalized.items():
                setattr(hotel, field_name, value)
        self._db.commit()
        return hotel

    def get_hotel(self, trip_id: UUID) -> HotelStay:
        trip = self.get_trip(trip_id)
        hotel = self._trips.get_hotel(trip.id)
        if hotel is None:
            raise AppError(404, "HOTEL_NOT_FOUND", "Hotel stay was not found.")
        return hotel

    def list_store_wishlist_products(self, store_id: UUID) -> list[Product]:
        self._require_user()
        if self._stores.get_active(store_id) is None:
            raise AppError(404, "STORE_NOT_FOUND", "Store was not found.")
        return [
            item.product
            for item in self._personalization.list_store_wishlist_products(
                DEMO_USER_ID,
                store_id,
            )
        ]

    def create_reservation(
        self,
        trip_id: UUID,
        *,
        store_id: UUID,
        scheduled_at: datetime,
        product_ids: list[str],
    ) -> VisitReservation:
        trip = self.get_trip(trip_id)
        store = self._stores.get_active_with_products(store_id)
        if store is None:
            raise AppError(404, "STORE_NOT_FOUND", "Store was not found.")

        ordered_product_ids = list(dict.fromkeys(product_ids))
        products = self._products.list_by_product_ids(ordered_product_ids)
        products_by_public_id = {product.product_id: product for product in products}
        missing_ids = set(ordered_product_ids) - products_by_public_id.keys()
        if missing_ids:
            raise AppError(404, "PRODUCT_NOT_FOUND", "A reservation product was not found.")

        wishlist_ids = {
            item.product_id for item in self._personalization.list_wishlist(DEMO_USER_ID)
        }
        store_product_ids = {item.product_id for item in store.store_products}
        invalid_products = [
            product
            for product in products
            if product.id not in wishlist_ids or product.id not in store_product_ids
        ]
        if invalid_products:
            raise AppError(
                400,
                "INVALID_RESERVATION_PRODUCTS",
                "Reservation products must be wishlisted and carried by the selected store.",
            )

        reservation = VisitReservation(
            user_id=DEMO_USER_ID,
            trip_id=trip.id,
            store=store,
            scheduled_at=scheduled_at.astimezone(UTC),
            status=ReservationStatus.RESERVED,
        )
        reservation.reservation_products = [
            VisitReservationProduct(product=products_by_public_id[product_id])
            for product_id in ordered_product_ids
        ]
        self._trips.add_reservation(reservation)
        self._db.commit()
        return reservation

    def list_reservations(self, trip_id: UUID) -> list[VisitReservation]:
        trip = self.get_trip(trip_id)
        return self._trips.list_reservations(DEMO_USER_ID, trip.id)

    def cancel_reservation(self, reservation_id: UUID) -> None:
        self._require_user()
        reservation = self._trips.get_reservation(DEMO_USER_ID, reservation_id)
        if reservation is None:
            raise AppError(404, "RESERVATION_NOT_FOUND", "Visit reservation was not found.")
        reservation.status = ReservationStatus.CANCELLED
        self._db.commit()

    def _require_user(self) -> None:
        if self._personalization.get_user(DEMO_USER_ID) is None:
            raise AppError(500, "DEMO_USER_NOT_CONFIGURED", "The demo user is not configured.")


def _normalize_datetime_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.astimezone(UTC) if isinstance(value, datetime) else value
        for key, value in values.items()
    }
