from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import Settings
from app.db.session import SessionLocal
from app.providers.openclip_embedding import OpenCLIPImageEmbedder
from app.repositories.product_embeddings import ProductEmbeddingRepository, ProductImageEmbedding
from app.repositories.products import ProductRepository

DEFAULT_REFERENCE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "openai"
DEFAULT_PRODUCT_IDS = (
    "demo_lotion_001",
    "demo_mouse_001",
    "demo_perfume_001",
)


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Index Product images into pgvector.")
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=DEFAULT_REFERENCE_DIR,
        help="Directory containing <product_id>_ref.jpg files.",
    )
    parser.add_argument(
        "--product-id",
        action="append",
        dest="product_ids",
        help="Product ID to index. Repeat for multiple products.",
    )
    args = parser.parse_args()
    product_ids = args.product_ids or list(DEFAULT_PRODUCT_IDS)
    embedder = OpenCLIPImageEmbedder(
        model_name=settings.openclip_model,
        pretrained=settings.openclip_pretrained,
        device=settings.openclip_device,
        expected_dimension=settings.openclip_embedding_dimension,
    )

    with SessionLocal() as db:
        products = ProductRepository(db)
        embeddings = ProductEmbeddingRepository(db)
        for product_id in product_ids:
            product = products.get_by_product_id(product_id)
            if product is None:
                raise SystemExit(f"Product not found: {product_id}")
            image_path = args.reference_dir / f"{product_id}_ref.jpg"
            if not image_path.is_file():
                raise SystemExit(f"Reference image not found: {image_path}")

            embedding = embedder.embed_sync(image_path.read_bytes())
            indexed_count = embeddings.replace_product(
                product_id=product.product_id,
                image_embeddings=[
                    ProductImageEmbedding(source_image=str(image_path), embedding=embedding)
                ],
            )
            print(
                f"indexed product_id={product_id} images={indexed_count} "
                f"dimensions={len(embedding)}"
            )


if __name__ == "__main__":
    main()
