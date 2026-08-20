import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.personalization import StoreProduct
from app.models.product import Product
from app.models.store import Store

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "products.seed.json"


class ProductSeed(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(alias="productId")
    sku: str
    brand: str
    name: str
    category: str
    image_url: str = Field(alias="imageUrl")
    price_krw: int = Field(alias="priceKrw", ge=0)
    estimated_refund_krw: int = Field(alias="estimatedRefundKrw", ge=0)
    tax_refund_supported: bool = Field(alias="taxRefundSupported")
    metadata_json: dict[str, object] = Field(default_factory=dict, alias="metadata")
    store_ids: list[UUID] | None = Field(default=None, alias="storeIds")


def seed_products(db: Session, seed_path: Path = DEFAULT_SEED_PATH) -> int:
    raw_products = json.loads(seed_path.read_text(encoding="utf-8"))
    products = TypeAdapter(list[ProductSeed]).validate_python(raw_products)

    all_store_ids = set(db.scalars(select(Store.id).order_by(Store.id)).all())
    for seed in products:
        product = db.scalar(select(Product).where(Product.product_id == seed.product_id))
        if product is None:
            product = Product(product_id=seed.product_id, sku=seed.sku)
            db.add(product)

        product.sku = seed.sku
        product.brand = seed.brand
        product.name = seed.name
        product.category = seed.category
        product.image_url = seed.image_url
        product.retail_price_krw = seed.price_krw
        product.estimated_refund_krw = seed.estimated_refund_krw
        product.tax_refund_supported = seed.tax_refund_supported
        product.metadata_json = seed.metadata_json
        db.flush()

        desired_store_ids = set(seed.store_ids) if seed.store_ids is not None else all_store_ids
        unknown_store_ids = desired_store_ids - all_store_ids
        if unknown_store_ids:
            unknown_store_id = min(unknown_store_ids, key=str)
            raise ValueError(f"Product seed references unknown store: {unknown_store_id}")

        current_mappings = list(
            db.scalars(select(StoreProduct).where(StoreProduct.product_id == product.id)).all()
        )
        current_store_ids = {mapping.store_id for mapping in current_mappings}

        for mapping in current_mappings:
            if mapping.store_id not in desired_store_ids:
                db.delete(mapping)

        for store_id in desired_store_ids - current_store_ids:
            db.add(StoreProduct(store_id=store_id, product_id=product.id))

    db.commit()
    return len(products)


def main() -> None:
    with SessionLocal() as db:
        seeded_count = seed_products(db)
    print(f"Seeded {seeded_count} products.")


if __name__ == "__main__":
    main()
