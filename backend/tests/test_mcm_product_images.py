from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import TriggerType
from app.models.personalization import StoreProduct
from app.models.product import Product
from app.models.shopping import SessionProduct, ShoppingSession
from app.scripts.seed_products import seed_products

MCM_STORE_IDS = {
    UUID("10000000-0000-0000-0000-000000000005"),
    UUID("10000000-0000-0000-0000-000000000008"),
}
MCM_IMAGE_URLS = {
    "MWSGSTA05BW001": ("http://1.201.116.58:8000/static/products/mcm/MWSGSTA05BW001.png"),
    "MPFGSMM04WT001": ("http://1.201.116.58:8000/static/products/mcm/MPFGSMM04WT001.png"),
    "MWHESTA03BK001": ("http://1.201.116.58:8000/static/products/mcm/MWHESTA03BK001.png"),
    "MWHGATA014B001": ("http://1.201.116.58:8000/static/products/mcm/MWHGATA014B001.png"),
    "MPFFSMM05CO001": ("http://1.201.116.58:8000/static/products/mcm/MPFFSMM05CO001.png"),
}


def _mcm_products_by_sku(db: Session) -> dict[str, Product]:
    products = db.scalars(select(Product).where(Product.sku.in_(MCM_IMAGE_URLS))).all()
    return {product.sku: product for product in products}


def _store_ids_for_product(db: Session, product: Product) -> set[UUID]:
    return set(
        db.scalars(select(StoreProduct.store_id).where(StoreProduct.product_id == product.id)).all()
    )


def test_static_mcm_product_images_are_served(client: TestClient) -> None:
    for sku in MCM_IMAGE_URLS:
        response = client.get(f"/static/products/mcm/{sku}.png")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_product_seed_upserts_only_expected_mcm_values(db_session: Session) -> None:
    products = _mcm_products_by_sku(db_session)
    assert products.keys() == MCM_IMAGE_URLS.keys()
    preserved_values = {
        sku: (
            product.product_id,
            product.brand,
            product.name,
            product.category,
            product.retail_price_krw,
            product.estimated_refund_krw,
            product.tax_refund_supported,
            product.metadata_json,
            _store_ids_for_product(db_session, product),
        )
        for sku, product in products.items()
    }
    for product in products.values():
        product.image_url = "https://old.example.test/product.png"
    db_session.commit()

    seed_products(db_session)

    products = _mcm_products_by_sku(db_session)
    for sku, product in products.items():
        assert product.image_url == MCM_IMAGE_URLS[sku]
        assert (
            product.product_id,
            product.brand,
            product.name,
            product.category,
            product.retail_price_krw,
            product.estimated_refund_krw,
            product.tax_refund_supported,
            product.metadata_json,
            _store_ids_for_product(db_session, product),
        ) == preserved_values[sku]
        assert _store_ids_for_product(db_session, product) == MCM_STORE_IDS


def test_session_products_api_returns_mcm_image_urls(
    client: TestClient,
    db_session: Session,
) -> None:
    shopping_session = ShoppingSession(
        store_id=UUID("10000000-0000-0000-0000-000000000005"),
        currency="CNY",
    )
    db_session.add(shopping_session)
    db_session.flush()
    observed_at = datetime(2026, 8, 21, tzinfo=UTC)
    for product in _mcm_products_by_sku(db_session).values():
        db_session.add(
            SessionProduct(
                session_id=shopping_session.id,
                product_id=product.id,
                first_observed_at=observed_at,
                last_observed_at=observed_at,
                max_occupancy_ratio=Decimal("0.2"),
                max_dwell_ms=1000,
                last_trigger_type=TriggerType.OCCUPANCY_AND_DWELL,
            )
        )
    db_session.commit()

    response = client.get(f"/api/v1/sessions/{shopping_session.id}/products")

    assert response.status_code == 200
    assert {
        item["product"]["sku"]: item["product"]["imageUrl"] for item in response.json()["items"]
    } == MCM_IMAGE_URLS
