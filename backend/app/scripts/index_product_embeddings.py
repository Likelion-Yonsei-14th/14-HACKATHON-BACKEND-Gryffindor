from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from app.core.config import Settings
from app.db.session import SessionLocal
from app.providers.openclip_embedding import OpenCLIPImageEmbedder
from app.repositories.product_embeddings import ProductEmbeddingRepository, ProductImageEmbedding
from app.repositories.products import ProductRepository

DEFAULT_REFERENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "recognition_refs"
DEFAULT_PRODUCT_IDS = (
    "diptyque_leau_papier_100_001",
    "dashu_aqua_dive_50_001",
    "anillo_fragrance_of_life_10_001",
    "hatchingroom_wavy_bag_mini_nylon_001",
    "zara_leather_tote_001",
)
SUPPORTED_REFERENCE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})


def find_reference_images(reference_dir: Path, product_id: str) -> list[Path]:
    product_reference_dir = reference_dir / product_id
    if not product_reference_dir.is_dir():
        raise SystemExit(
            f"Reference directory not found for product_id={product_id}: "
            f"expected_directory={product_reference_dir}"
        )

    image_paths = sorted(
        (
            path
            for path in product_reference_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_REFERENCE_EXTENSIONS
        ),
        key=lambda path: path.name,
    )
    if not image_paths:
        raise SystemExit(
            f"No reference images found for product_id={product_id}: "
            f"expected_directory={product_reference_dir} "
            f"supported_extensions={','.join(sorted(SUPPORTED_REFERENCE_EXTENSIONS))}"
        )
    return image_paths


def main(argv: Sequence[str] | None = None) -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Index Product images into pgvector.")
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=DEFAULT_REFERENCE_DIR,
        help="Directory containing <product_id>/ reference image directories.",
    )
    parser.add_argument(
        "--product-id",
        action="append",
        dest="product_ids",
        help="Product ID to index. Repeat for multiple products.",
    )
    args = parser.parse_args(argv)
    reference_dir = cast(Path, args.reference_dir)
    requested_product_ids = cast(list[str] | None, args.product_ids)
    product_ids = requested_product_ids or list(DEFAULT_PRODUCT_IDS)
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

            image_embeddings: list[ProductImageEmbedding] = []
            for image_path in find_reference_images(reference_dir, product_id):
                embedding = embedder.embed_sync(image_path.read_bytes())
                image_embeddings.append(
                    ProductImageEmbedding(source_image=str(image_path), embedding=embedding)
                )

            indexed_count = embeddings.replace_product(
                product_id=product.product_id,
                image_embeddings=image_embeddings,
            )
            print(
                f"indexed product_id={product_id} images={indexed_count} "
                f"dimensions={len(image_embeddings[0].embedding)}"
            )


if __name__ == "__main__":
    main()
