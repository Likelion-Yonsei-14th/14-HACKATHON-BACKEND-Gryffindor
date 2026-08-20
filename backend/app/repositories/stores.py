from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.personalization import StoreProduct
from app.models.store import Store


class StoreRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, store_id: UUID) -> Store | None:
        return self._db.get(Store, store_id)

    def get_active(self, store_id: UUID) -> Store | None:
        statement = select(Store).where(
            Store.id == store_id,
            Store.is_active.is_(True),
        )
        return self._db.scalar(statement)

    def get_with_products(self, store_id: UUID) -> Store | None:
        statement = (
            select(Store)
            .options(joinedload(Store.store_products).joinedload(StoreProduct.product))
            .where(Store.id == store_id)
        )
        return self._db.scalars(statement).unique().one_or_none()

    def get_active_with_products(self, store_id: UUID) -> Store | None:
        statement = (
            select(Store)
            .options(joinedload(Store.store_products).joinedload(StoreProduct.product))
            .where(
                Store.id == store_id,
                Store.is_active.is_(True),
            )
        )
        return self._db.scalars(statement).unique().one_or_none()

    def list_all(self) -> list[Store]:
        statement = select(Store).order_by(Store.id)
        return list(self._db.scalars(statement).all())

    def list_active(self) -> list[Store]:
        statement = select(Store).where(Store.is_active.is_(True)).order_by(Store.id)
        return list(self._db.scalars(statement).all())
