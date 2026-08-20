from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.personalization import StoreProduct
from app.models.product import Product
from app.scripts.seed_products import seed_products

MCM_STORE_IDS = {
    UUID("10000000-0000-0000-0000-000000000005"),
    UUID("10000000-0000-0000-0000-000000000008"),
}
MCM_PRODUCT_IDS = {
    "mcm_aren_lambskin_shoulder_s_001",
    "mcm_cosmic_star_edp_75_001",
    "mcm_aren_maxi_monogram_leather_hobo_s_001",
    "mcm_aren_duo_hobo_maxi_visetos_calfskin_s_001",
    "mcm_jolly_rabbit_100_001",
}
RECOGNITION_PRODUCT_IDS = {
    "diptyque_leau_papier_100_001",
    "dashu_aqua_dive_50_001",
    "anillo_fragrance_of_life_10_001",
    "hatchingroom_wavy_bag_mini_nylon_001",
    "zara_leather_tote_001",
    "vivienne_westwood_wallet_5115002ew_001",
    "dior_saddle_bloom_card_wallet_s5611ctzq_m928_001",
    "dior_beauty_velvet_pouch_black_001",
}


def _store_ids_for_product(db: Session, product: Product) -> set[UUID]:
    return set(
        db.scalars(select(StoreProduct.store_id).where(StoreProduct.product_id == product.id)).all()
    )


def test_product_seed_adds_catalog_and_is_idempotent(db_session: Session) -> None:
    first_count = db_session.scalar(select(func.count()).select_from(Product))

    seeded_count = seed_products(db_session)
    second_count = db_session.scalar(select(func.count()).select_from(Product))
    products = {
        product.product_id: product for product in db_session.scalars(select(Product)).all()
    }

    expected_count = len(MCM_PRODUCT_IDS | RECOGNITION_PRODUCT_IDS)
    assert first_count == expected_count
    assert seeded_count == expected_count
    assert second_count == expected_count
    assert MCM_PRODUCT_IDS <= products.keys()
    assert RECOGNITION_PRODUCT_IDS <= products.keys()

    for product_id in MCM_PRODUCT_IDS:
        product = products[product_id]
        assert product.brand == "MCM"
        assert product.estimated_refund_krw == 0
        assert product.tax_refund_supported is False
        assert _store_ids_for_product(db_session, product) == MCM_STORE_IDS

    for product_id, product in products.items():
        if product_id not in MCM_PRODUCT_IDS:
            assert _store_ids_for_product(db_session, product) == set()


def test_product_seed_removes_stale_store_product_relations(db_session: Session) -> None:
    recognition_product = db_session.scalar(
        select(Product).where(Product.product_id == "diptyque_leau_papier_100_001")
    )
    mcm_product = db_session.scalar(
        select(Product).where(Product.product_id == "mcm_aren_lambskin_shoulder_s_001")
    )
    assert recognition_product is not None
    assert mcm_product is not None

    stale_store_id = UUID("10000000-0000-0000-0000-000000000001")
    missing_desired_store_id = UUID("10000000-0000-0000-0000-000000000005")
    desired_mapping = db_session.get(
        StoreProduct,
        (missing_desired_store_id, mcm_product.id),
    )
    assert desired_mapping is not None
    db_session.delete(desired_mapping)
    db_session.add(StoreProduct(store_id=stale_store_id, product_id=recognition_product.id))
    db_session.add(StoreProduct(store_id=stale_store_id, product_id=mcm_product.id))
    db_session.commit()

    assert seed_products(db_session) == len(MCM_PRODUCT_IDS | RECOGNITION_PRODUCT_IDS)
    assert _store_ids_for_product(db_session, recognition_product) == set()
    assert _store_ids_for_product(db_session, mcm_product) == MCM_STORE_IDS

    assert seed_products(db_session) == len(MCM_PRODUCT_IDS | RECOGNITION_PRODUCT_IDS)
    assert _store_ids_for_product(db_session, recognition_product) == set()
    assert _store_ids_for_product(db_session, mcm_product) == MCM_STORE_IDS
