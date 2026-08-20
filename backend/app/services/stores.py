from sqlalchemy.orm import Session

from app.models.store import Store
from app.repositories.stores import StoreRepository
from app.services.geo import haversine_distance_km


class StoreService:
    def __init__(self, db: Session) -> None:
        self._stores = StoreRepository(db)

    def list_stores(self) -> list[Store]:
        return self._stores.list_active()

    def list_nearby_stores(
        self,
        latitude: float,
        longitude: float,
        limit: int,
    ) -> list[tuple[Store, float]]:
        nearby_stores = [
            (store, distance)
            for store in self._stores.list_active()
            if (
                distance := haversine_distance_km(
                    latitude,
                    longitude,
                    store.latitude,
                    store.longitude,
                )
            )
            is not None
        ]
        nearby_stores.sort(key=lambda item: (item[1], str(item[0].id)))
        return nearby_stores[:limit]
