from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.scripts.seed_products import seed_products


def test_product_seed_contains_three_products_and_is_idempotent(db_session: Session) -> None:
    first_count = db_session.scalar(select(func.count()).select_from(Product))

    seeded_count = seed_products(db_session)
    second_count = db_session.scalar(select(func.count()).select_from(Product))

    assert first_count == 3
    assert seeded_count == 3
    assert second_count == 3
