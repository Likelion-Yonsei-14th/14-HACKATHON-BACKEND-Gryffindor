from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.product_embedding import ProductEmbedding

EMBEDDING_DIMENSION = 512


@dataclass(frozen=True, slots=True)
class ProductImageEmbedding:
    source_image: str
    embedding: Sequence[float]


@dataclass(frozen=True, slots=True)
class ProductEmbeddingMatch:
    product_id: str
    cosine_distance: float

    @property
    def similarity(self) -> float:
        return 1.0 - self.cosine_distance


class ProductEmbeddingRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def replace_product(
        self,
        *,
        product_id: str,
        image_embeddings: Sequence[ProductImageEmbedding],
    ) -> int:
        normalized_product_id = product_id.strip()
        if not normalized_product_id:
            raise ValueError("product_id must not be empty")
        if not image_embeddings:
            raise ValueError("at least one image embedding is required")

        records = [
            ProductEmbedding(
                product_id=normalized_product_id,
                source_image=item.source_image,
                embedding=self._validate_embedding(item.embedding),
            )
            for item in image_embeddings
        ]
        try:
            self._db.execute(
                delete(ProductEmbedding).where(ProductEmbedding.product_id == normalized_product_id)
            )
            self._db.add_all(records)
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        return len(records)

    def search(
        self,
        *,
        embedding: list[float],
        candidate_product_ids: list[str],
        limit: int = 2,
    ) -> list[ProductEmbeddingMatch]:
        if not candidate_product_ids:
            return []

        vector = self._validate_embedding(embedding)
        distance = ProductEmbedding.embedding.cosine_distance(vector).label("distance")
        statement = select(ProductEmbedding.product_id, distance).where(
            ProductEmbedding.product_id.in_(candidate_product_ids)
        )
        rows = [
            (str(product_id), float(cosine_distance))
            for product_id, cosine_distance in self._db.execute(statement).all()
        ]
        return select_best_product_matches(rows, limit=limit)

    def count(self) -> int:
        return sum(1 for _ in self._db.scalars(select(ProductEmbedding.product_id)))

    @staticmethod
    def _validate_embedding(embedding: Sequence[float]) -> list[float]:
        vector = [float(value) for value in embedding]
        if len(vector) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"embedding must contain {EMBEDDING_DIMENSION} values, got {len(vector)}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("embedding values must be finite")
        return vector


def select_best_product_matches(
    rows: Sequence[tuple[str, float]],
    *,
    limit: int,
) -> list[ProductEmbeddingMatch]:
    best_by_product: dict[str, float] = {}
    for product_id, cosine_distance in rows:
        if product_id not in best_by_product or cosine_distance < best_by_product[product_id]:
            best_by_product[product_id] = cosine_distance
    return [
        ProductEmbeddingMatch(product_id=product_id, cosine_distance=cosine_distance)
        for product_id, cosine_distance in sorted(
            best_by_product.items(), key=lambda item: item[1]
        )[:limit]
    ]
