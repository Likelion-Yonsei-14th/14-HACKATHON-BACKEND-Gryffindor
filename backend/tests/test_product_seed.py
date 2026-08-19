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
    refund_rows = db_session.execute(
        select(Product.product_id, Product.estimated_refund_krw)
    ).tuples()
    refund_amounts = {
        product_id: estimated_refund_krw
        for product_id, estimated_refund_krw in refund_rows
    }

    assert first_count == 12
    assert seeded_count == 12
    assert second_count == 12
    assert demo_product_ids == {
        "demo_bag_001",
        "demo_bag_002",
        "demo_bag_003",
        "demo_lotion_001",
        "demo_mouse_001",
        "demo_perfume_001",
        "demo_perfume_002",
        "demo_perfume_003",
        "demo_perfume_004",
    }
    assert {
        product_id: refund_amounts[product_id]
        for product_id in {
            "test_outer_001",
            "test_outer_002",
            "test_outer_003",
            "demo_mouse_001",
            "demo_perfume_001",
            "demo_lotion_001",
        }
    } == {
        "test_outer_001": 0,
        "test_outer_002": 0,
        "test_outer_003": 0,
        "demo_mouse_001": 1_000,
        "demo_perfume_001": 13_000,
        "demo_lotion_001": 1_000,
    }
    assert refund_amounts["demo_bag_001"] == 62_000
    assert refund_amounts["demo_perfume_002"] == 15_000
