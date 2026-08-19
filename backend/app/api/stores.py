from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.api import StoreListResponse, StoreResponse
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
