import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.store import Store
from app.scripts.seed_stores import StoreSeed, seed_stores


def test_store_seed_adds_production_stores_and_is_idempotent(db_session: Session) -> None:
    first_count = db_session.scalar(select(func.count()).select_from(Store))

    seeded_count = seed_stores(db_session)
    second_count = db_session.scalar(select(func.count()).select_from(Store))
    stores = db_session.scalars(select(Store).order_by(Store.id)).all()

    assert first_count == 8
    assert seeded_count == 8
    assert second_count == 8
    assert [store.name for store in stores[:3]] == [
        "Ferragamo 현대백화점 신촌점",
        "OMEGA 현대백화점 신촌점",
        "MCM 롯데면세점 명동본점",
    ]
    assert {store.type for store in stores} == {"DEPARTMENT_STORE", "DUTY_FREE"}
    assert stores[-1].terminal == "T1"
    assert stores[-1].latitude is not None
    assert all(store.image_url for store in stores)
    assert all(store.is_active is True for store in stores)


def test_store_seed_parses_and_persists_image_url(
    db_session: Session,
    tmp_path: Path,
) -> None:
    store_id = UUID("20000000-0000-0000-0000-000000000001")
    image_url = "https://cdn.example.test/stores/mcm.jpg"
    raw_store = {
        "id": str(store_id),
        "name": "Image Test Store",
        "brand": "MCM",
        "country": "KR",
        "city": "Seoul",
        "type": "DUTY_FREE",
        "airportCode": None,
        "imageUrl": image_url,
    }
    parsed = StoreSeed.model_validate(raw_store)
    assert parsed.image_url == image_url
    assert parsed.is_active is True

    seed_path = tmp_path / "stores.seed.json"
    seed_path.write_text(json.dumps([raw_store]), encoding="utf-8")

    assert seed_stores(db_session, seed_path) == 1
    assert seed_stores(db_session, seed_path) == 1
    store = db_session.get(Store, store_id)
    assert store is not None
    assert store.image_url == image_url
    assert store.is_active is True
    assert (
        db_session.scalar(select(func.count()).select_from(Store).where(Store.id == store_id)) == 1
    )


def test_store_seed_preserves_unlisted_inactive_legacy_store(db_session: Session) -> None:
    legacy_store_id = UUID("10000000-0000-0000-0000-000000000002")
    db_session.add(
        Store(
            id=legacy_store_id,
            name="MCM New York",
            brand="MCM",
            country="US",
            city="New York",
            type="CITY",
            is_active=False,
        )
    )
    db_session.commit()

    assert seed_stores(db_session) == 8
    assert seed_stores(db_session) == 8

    legacy_store = db_session.get(Store, legacy_store_id)
    assert legacy_store is not None
    assert legacy_store.name == "MCM New York"
    assert legacy_store.is_active is False
    assert db_session.scalar(select(func.count()).select_from(Store)) == 9
