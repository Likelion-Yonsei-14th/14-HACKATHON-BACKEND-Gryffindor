from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product


class ProductRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_all(self) -> list[Product]:
        statement = select(Product).order_by(Product.product_id)
        return list(self._db.scalars(statement).all())

    def get_by_product_id(self, product_id: str) -> Product | None:
        statement = select(Product).where(Product.product_id == product_id)
        return self._db.scalar(statement)

    def list_by_product_ids(self, product_ids: list[str]) -> list[Product]:
        if not product_ids:
            return []
        statement = select(Product).where(Product.product_id.in_(product_ids))
        return list(self._db.scalars(statement).all())

    def list_by_ids(self, product_ids: set[UUID]) -> list[Product]:
        if not product_ids:
            return []
        statement = select(Product).where(Product.id.in_(product_ids))
        return list(self._db.scalars(statement).all())
