from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.trip import HotelStay, Trip, VisitReservation, VisitReservationProduct


class TripRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, trip: Trip) -> Trip:
        self._db.add(trip)
        self._db.flush()
        return trip

    def get(self, user_id: int, trip_id: UUID) -> Trip | None:
        statement = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
        return self._db.scalar(statement)

    def get_detail(self, user_id: int, trip_id: UUID) -> Trip | None:
        statement = (
            select(Trip)
            .options(
                selectinload(Trip.flights),
                joinedload(Trip.hotel),
                selectinload(Trip.visit_reservations).joinedload(VisitReservation.store),
                selectinload(Trip.visit_reservations)
                .selectinload(VisitReservation.reservation_products)
                .joinedload(VisitReservationProduct.product),
            )
            .where(Trip.id == trip_id, Trip.user_id == user_id)
        )
        return self._db.scalars(statement).unique().one_or_none()

    def list_trips(self, user_id: int) -> list[Trip]:
        statement = (
            select(Trip)
            .where(Trip.user_id == user_id)
            .order_by(Trip.starts_at.desc().nullslast(), Trip.created_at.desc(), Trip.id.desc())
        )
        return list(self._db.scalars(statement).all())

    def add_hotel(self, hotel: HotelStay) -> HotelStay:
        self._db.add(hotel)
        self._db.flush()
        return hotel

    def get_hotel(self, trip_id: UUID) -> HotelStay | None:
        statement = select(HotelStay).where(HotelStay.trip_id == trip_id)
        return self._db.scalar(statement)

    def add_reservation(self, reservation: VisitReservation) -> VisitReservation:
        self._db.add(reservation)
        self._db.flush()
        return reservation

    def get_reservation(self, user_id: int, reservation_id: UUID) -> VisitReservation | None:
        statement = (
            select(VisitReservation)
            .options(
                joinedload(VisitReservation.store),
                selectinload(VisitReservation.reservation_products).joinedload(
                    VisitReservationProduct.product
                ),
            )
            .where(
                VisitReservation.id == reservation_id,
                VisitReservation.user_id == user_id,
            )
        )
        return self._db.scalars(statement).unique().one_or_none()

    def list_reservations(self, user_id: int, trip_id: UUID) -> list[VisitReservation]:
        statement = (
            select(VisitReservation)
            .options(
                joinedload(VisitReservation.store),
                selectinload(VisitReservation.reservation_products).joinedload(
                    VisitReservationProduct.product
                ),
            )
            .where(
                VisitReservation.user_id == user_id,
                VisitReservation.trip_id == trip_id,
            )
            .order_by(VisitReservation.scheduled_at, VisitReservation.created_at)
        )
        return list(self._db.scalars(statement).unique().all())
