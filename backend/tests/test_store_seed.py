from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.store import Store
from app.scripts.seed_stores import seed_stores


def test_store_seed_adds_demo_stores_and_is_idempotent(db_session: Session) -> None:
    first_count = db_session.scalar(select(func.count()).select_from(Store))

    seeded_count = seed_stores(db_session)
    second_count = db_session.scalar(select(func.count()).select_from(Store))
    stores = db_session.scalars(select(Store).order_by(Store.id)).all()

    assert first_count == 10
    assert seeded_count == 10
    assert second_count == 10
    assert [store.name for store in stores[:3]] == [
        "MCM Seoul",
        "MCM New York",
        "MCM Airport Store",
    ]
    assert stores[2].type == "AIRPORT"
    assert stores[2].airport_code == "ICN"
    assert {store.type for store in stores[3:]} == {"DEPARTMENT_STORE", "DUTY_FREE"}
    assert stores[-1].terminal == "T2"
    assert stores[-1].latitude is not None
