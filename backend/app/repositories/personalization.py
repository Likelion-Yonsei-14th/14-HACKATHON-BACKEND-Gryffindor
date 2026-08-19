from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.personalization import (
    Flight,
    Receipt,
    ReceiptItem,
    StoreProduct,
    User,
    WishlistItem,
)
from app.models.shopping import SessionProduct, ShoppingSession
from app.models.store import Store


class PersonalizationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_user(self, user_id: int) -> User | None:
        return self._db.get(User, user_id)

    def list_wishlist(self, user_id: int) -> list[WishlistItem]:
        statement = (
            select(WishlistItem)
            .options(joinedload(WishlistItem.product))
            .where(WishlistItem.user_id == user_id)
            .order_by(WishlistItem.created_at, WishlistItem.id)
        )
        return list(self._db.scalars(statement).all())

    def get_wishlist_item(self, user_id: int, product_id: UUID) -> WishlistItem | None:
        statement = select(WishlistItem).where(
            WishlistItem.user_id == user_id,
            WishlistItem.product_id == product_id,
        )
        return self._db.scalar(statement)

    def add_wishlist_item(self, item: WishlistItem) -> WishlistItem:
        self._db.add(item)
        self._db.flush()
        return item

    def delete_wishlist_item(self, item: WishlistItem) -> None:
        self._db.delete(item)
        self._db.flush()

    def add_receipt(self, receipt: Receipt) -> Receipt:
        self._db.add(receipt)
        self._db.flush()
        return receipt

    def list_receipts(self, user_id: int) -> list[Receipt]:
        statement = (
            select(Receipt)
            .options(selectinload(Receipt.items).joinedload(ReceiptItem.product))
            .where(Receipt.user_id == user_id)
            .order_by(Receipt.created_at.desc(), Receipt.id.desc())
        )
        return list(self._db.scalars(statement).all())

    def get_receipt(self, user_id: int, receipt_id: UUID) -> Receipt | None:
        statement = (
            select(Receipt)
            .options(selectinload(Receipt.items).joinedload(ReceiptItem.product))
            .where(Receipt.id == receipt_id, Receipt.user_id == user_id)
        )
        return self._db.scalar(statement)

    def list_trip_receipts(self, user_id: int, trip_id: UUID) -> list[Receipt]:
        statement = (
            select(Receipt)
            .options(selectinload(Receipt.items).joinedload(ReceiptItem.product))
            .where(Receipt.user_id == user_id, Receipt.trip_id == trip_id)
            .order_by(Receipt.created_at, Receipt.id)
        )
        return list(self._db.scalars(statement).all())

    def add_flight(self, flight: Flight) -> Flight:
        self._db.add(flight)
        self._db.flush()
        return flight

    def get_flight(self, user_id: int, flight_id: UUID) -> Flight | None:
        statement = select(Flight).where(
            Flight.id == flight_id,
            Flight.user_id == user_id,
        )
        return self._db.scalar(statement)

    def latest_flight(self, user_id: int) -> Flight | None:
        statement = (
            select(Flight)
            .where(Flight.user_id == user_id)
            .order_by(Flight.created_at.desc(), Flight.id.desc())
            .limit(1)
        )
        return self._db.scalar(statement)

    def latest_trip_flight(self, user_id: int, trip_id: UUID) -> Flight | None:
        statement = (
            select(Flight)
            .where(Flight.user_id == user_id, Flight.trip_id == trip_id)
            .order_by(Flight.created_at.desc(), Flight.id.desc())
            .limit(1)
        )
        return self._db.scalar(statement)

    def list_recent_session_products(
        self,
        user_id: int,
        *,
        session_limit: int = 10,
    ) -> list[SessionProduct]:
        recent_session_ids = (
            select(ShoppingSession.id)
            .where(ShoppingSession.user_id == user_id)
            .order_by(ShoppingSession.started_at.desc(), ShoppingSession.id.desc())
            .limit(session_limit)
        )
        statement = (
            select(SessionProduct)
            .options(
                joinedload(SessionProduct.product),
                joinedload(SessionProduct.shopping_session).joinedload(ShoppingSession.store),
            )
            .where(SessionProduct.session_id.in_(recent_session_ids))
            .order_by(SessionProduct.last_observed_at.desc())
        )
        return list(self._db.scalars(statement).all())

    def list_candidate_stores(self) -> list[Store]:
        statement = (
            select(Store)
            .options(joinedload(Store.store_products).joinedload(StoreProduct.product))
            .order_by(Store.id)
        )
        return list(self._db.scalars(statement).unique().all())

    def list_store_wishlist_products(self, user_id: int, store_id: UUID) -> list[WishlistItem]:
        statement = (
            select(WishlistItem)
            .join(
                StoreProduct,
                StoreProduct.product_id == WishlistItem.product_id,
            )
            .options(joinedload(WishlistItem.product))
            .where(
                WishlistItem.user_id == user_id,
                StoreProduct.store_id == store_id,
            )
            .order_by(WishlistItem.created_at, WishlistItem.id)
        )
        return list(self._db.scalars(statement).all())
