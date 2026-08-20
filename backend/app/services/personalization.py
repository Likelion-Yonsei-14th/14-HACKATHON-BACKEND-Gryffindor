from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import SINGLE_USER_ID
from app.domain.enums import RefundMethod
from app.errors import AppError
from app.models.personalization import Flight, Receipt, ReceiptItem, User, WishlistItem
from app.models.product import Product
from app.models.shopping import SessionProduct
from app.providers.documents import (
    DocumentExtractionProvider,
    DocumentExtractionProviderError,
)
from app.repositories.personalization import PersonalizationRepository
from app.repositories.products import ProductRepository
from app.repositories.trips import TripRepository


class PersonalizationService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._personalization = PersonalizationRepository(db)
        self._products = ProductRepository(db)
        self._trips = TripRepository(db)

    def user(self) -> User:
        user = self._personalization.get_user(SINGLE_USER_ID)
        if user is None:
            raise AppError(500, "SINGLE_USER_NOT_CONFIGURED", "The single user is not configured.")
        return user

    def list_wishlist(self) -> list[WishlistItem]:
        self.user()
        return self._personalization.list_wishlist(SINGLE_USER_ID)

    def add_wishlist(self, public_product_id: str) -> Product:
        self.user()
        product = self._products.get_by_product_id(public_product_id)
        if product is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "Product was not found.")

        existing = self._personalization.get_wishlist_item(SINGLE_USER_ID, product.id)
        if existing is None:
            self._personalization.add_wishlist_item(
                WishlistItem(user_id=SINGLE_USER_ID, product_id=product.id)
            )
            try:
                self._db.commit()
            except IntegrityError:
                self._db.rollback()
        return product

    def delete_wishlist(self, public_product_id: str) -> None:
        self.user()
        product = self._products.get_by_product_id(public_product_id)
        if product is None:
            return
        item = self._personalization.get_wishlist_item(SINGLE_USER_ID, product.id)
        if item is not None:
            self._personalization.delete_wishlist_item(item)
            self._db.commit()

    async def analyze_receipt(
        self,
        image_bytes: bytes,
        provider: DocumentExtractionProvider,
        trip_id: UUID | None = None,
    ) -> Receipt:
        self.user()
        if trip_id is not None and self._trips.get(SINGLE_USER_ID, trip_id) is None:
            raise AppError(404, "TRIP_NOT_FOUND", "Trip was not found.")
        try:
            extraction = await provider.extract_receipt(image_bytes)
        except DocumentExtractionProviderError as exc:
            raise _document_provider_error() from exc

        products_by_name = _products_by_exact_name(self._products.list_all())
        receipt = Receipt(
            user_id=SINGLE_USER_ID,
            trip_id=trip_id,
            store_name=extraction.store_name,
            purchased_at=_as_utc(extraction.purchased_at),
            total_amount=extraction.total_amount,
            currency=extraction.currency,
            image_path=None,
        )
        for extracted_item in extraction.items:
            product = products_by_name.get(_normalize_product_name(extracted_item.name))
            receipt.items.append(
                ReceiptItem(
                    product_name=extracted_item.name,
                    product=product,
                    quantity=extracted_item.quantity,
                    price=extracted_item.price,
                )
            )
        self._personalization.add_receipt(receipt)
        self._db.commit()
        return receipt

    async def analyze_flight(
        self,
        image_bytes: bytes,
        provider: DocumentExtractionProvider,
        trip_id: UUID | None = None,
    ) -> Flight:
        self.user()
        if trip_id is not None and self._trips.get(SINGLE_USER_ID, trip_id) is None:
            raise AppError(404, "TRIP_NOT_FOUND", "Trip was not found.")
        try:
            extraction = await provider.extract_flight(image_bytes)
        except DocumentExtractionProviderError as exc:
            raise _document_provider_error() from exc

        flight = self._personalization.add_flight(
            Flight(
                user_id=SINGLE_USER_ID,
                trip_id=trip_id,
                departure_airport=extraction.departure_airport,
                arrival_airport=extraction.arrival_airport,
                terminal=extraction.terminal,
                flight_number=extraction.flight_number,
                departure_at=_as_utc(extraction.departure_at),
                arrival_at=_as_utc(extraction.arrival_at),
                airport_arrival_at=None,
            )
        )
        self._db.commit()
        return flight

    def update_flight(self, flight_id: UUID, changes: dict[str, Any]) -> Flight:
        self.user()
        flight = self._personalization.get_flight(SINGLE_USER_ID, flight_id)
        if flight is None:
            raise AppError(404, "FLIGHT_NOT_FOUND", "Flight was not found.")

        for field_name, value in changes.items():
            if field_name in {"departure_at", "arrival_at", "airport_arrival_at"}:
                value = _as_utc(value)
            setattr(flight, field_name, value)
        self._db.commit()
        return flight

    def list_receipts(self) -> list[Receipt]:
        self.user()
        return self._personalization.list_receipts(SINGLE_USER_ID)

    def list_purchases(self) -> list[Receipt]:
        return self.list_receipts()

    def list_session_purchased_products(self) -> list[SessionProduct]:
        """Return the Single User's SessionProducts with purchase_state == PURCHASED."""
        return self._personalization.list_session_purchased_products(SINGLE_USER_ID)

    def update_purchase_refund_method(
        self,
        purchase_id: UUID,
        refund_method: RefundMethod,
    ) -> Receipt:
        self.user()
        purchase = self._personalization.get_receipt(SINGLE_USER_ID, purchase_id)
        if purchase is None:
            raise AppError(404, "PURCHASE_NOT_FOUND", "Purchase was not found.")
        purchase.refund_method = refund_method
        self._db.commit()
        return purchase

    def latest_flight(self) -> Flight | None:
        self.user()
        return self._personalization.latest_flight(SINGLE_USER_ID)


def _products_by_exact_name(products: list[Product]) -> dict[str, Product]:
    matches: dict[str, list[Product]] = {}
    for product in products:
        matches.setdefault(_normalize_product_name(product.name), []).append(product)
    return {name: items[0] for name, items in matches.items() if len(items) == 1}


def _normalize_product_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC)


def _document_provider_error() -> AppError:
    return AppError(
        503,
        "DOCUMENT_EXTRACTION_PROVIDER_ERROR",
        "The document extraction provider is temporarily unavailable.",
    )
