from sqlalchemy.orm import Session

from app.models.store import Store
from app.repositories.stores import StoreRepository


class StoreService:
    def __init__(self, db: Session) -> None:
        self._stores = StoreRepository(db)

    def list_stores(self) -> list[Store]:
        return self._stores.list_all()
