from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.scripts.seed_products import seed_products


def test_product_seed_adds_a4_demo_products_and_is_idempotent(db_session: Session) -> None:
    first_count = db_session.scalar(select(func.count()).select_from(Product))

    seeded_count = seed_products(db_session)
    second_count = db_session.scalar(select(func.count()).select_from(Product))
    demo_product_ids = set(
        db_session.scalars(
            select(Product.product_id).where(Product.product_id.like("demo_%"))
        ).all()
    )

    assert first_count == 6
    assert seeded_count == 6
    assert second_count == 6
    assert demo_product_ids == {
        "demo_lotion_001",
        "demo_mouse_001",
        "demo_perfume_001",
    }
