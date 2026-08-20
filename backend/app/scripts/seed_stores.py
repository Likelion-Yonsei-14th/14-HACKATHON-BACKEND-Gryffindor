import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.store import Store

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "stores.seed.json"


class StoreSeed(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    name: str
    brand: str
    country: str
    city: str | None
    type: str
    airport_code: str | None = Field(alias="airportCode")
    address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    terminal: str | None = None
    opening_hours: str | None = Field(default=None, alias="openingHours")
    image_url: str | None = Field(default=None, alias="imageUrl")
    is_active: bool = Field(default=True, alias="isActive")


def seed_stores(db: Session, seed_path: Path = DEFAULT_SEED_PATH) -> int:
    raw_stores = json.loads(seed_path.read_text(encoding="utf-8"))
    stores = TypeAdapter(list[StoreSeed]).validate_python(raw_stores)

    for seed in stores:
        store = db.get(Store, seed.id)
        if store is None:
            store = Store(id=seed.id)
            db.add(store)

        store.name = seed.name
        store.brand = seed.brand
        store.country = seed.country
        store.city = seed.city
        store.type = seed.type
        store.airport_code = seed.airport_code
        store.address = seed.address
        store.latitude = seed.latitude
        store.longitude = seed.longitude
        store.terminal = seed.terminal
        store.opening_hours = seed.opening_hours
        store.image_url = seed.image_url
        store.is_active = seed.is_active

    db.commit()
    return len(stores)


def main() -> None:
    with SessionLocal() as db:
        seeded_count = seed_stores(db)
    print(f"Seeded {seeded_count} stores.")


if __name__ == "__main__":
    main()
