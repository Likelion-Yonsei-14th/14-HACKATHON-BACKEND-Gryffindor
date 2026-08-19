from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.api import NearbyStoreResponse, StoreListResponse, StoreResponse
from app.services.stores import StoreService

router = APIRouter(prefix="/api/v1", tags=["stores"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("/stores", response_model=StoreListResponse)
def list_stores(db: DbSession) -> StoreListResponse:
    stores = StoreService(db).list_stores()
    return StoreListResponse(
        stores=[
            StoreResponse(
                id=store.id,
                name=store.name,
                brand=store.brand,
                country=store.country,
                city=store.city,
                type=store.type,
                airport_code=store.airport_code,
                address=store.address,
                latitude=store.latitude,
                longitude=store.longitude,
                terminal=store.terminal,
                opening_hours=store.opening_hours,
            )
            for store in stores
        ]
    )


@router.get("/stores/nearby", response_model=list[NearbyStoreResponse])
def list_nearby_stores(
    db: DbSession,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[NearbyStoreResponse]:
    return [
        NearbyStoreResponse(
            store_id=store.id,
            name=store.name,
            type=store.type,
            address=store.address,
            latitude=store.latitude,
            longitude=store.longitude,
            distance_km=distance,
            airport_code=store.airport_code,
            terminal=store.terminal,
        )
        for store, distance in StoreService(db).list_nearby_stores(latitude, longitude, limit)
    ]
