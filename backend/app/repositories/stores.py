from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.store import Store


class StoreRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, store_id: UUID) -> Store | None:
        return self._db.get(Store, store_id)

    def list_all(self) -> list[Store]:
        statement = select(Store).order_by(Store.id)
        return list(self._db.scalars(statement).all())
