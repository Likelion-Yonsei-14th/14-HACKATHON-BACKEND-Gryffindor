from __future__ import annotations

from dataclasses import replace
from time import perf_counter
from typing import Protocol

from app.domain.enums import RecognitionStatus
from app.providers.openclip_embedding import OpenCLIPImageEmbedder
from app.providers.recognition import (
    RecognitionCandidate,
    RecognitionDecision,
    RecognitionProvider,
    RecognitionTelemetry,
)
from app.repositories.product_embeddings import ProductEmbeddingMatch, ProductEmbeddingRepository


class ImageEmbedder(Protocol):
    async def embed(self, image_bytes: bytes) -> list[float]: ...


class EmbeddingSearcher(Protocol):
    def search(
        self,
        *,
        embedding: list[float],
        candidate_product_ids: list[str],
        limit: int = 2,
    ) -> list[ProductEmbeddingMatch]: ...


class OpenCLIPRecognitionProvider:
    def __init__(
        self,
        *,
        embedder: ImageEmbedder | OpenCLIPImageEmbedder,
        searcher: EmbeddingSearcher | ProductEmbeddingRepository,
        match_threshold: float,
        margin_threshold: float,
        fallback: RecognitionProvider | None = None,
    ) -> None:
        self._embedder = embedder
        self._searcher = searcher
        self._fallback = fallback
        self._match_threshold = match_threshold
        self._margin_threshold = margin_threshold

    async def close(self) -> None:
        if self._fallback is None:
            return
        close = getattr(self._fallback, "close", None)
        if close is not None:
            await close()

    async def recognize(
        self,
        image_bytes: bytes,
        candidates: list[RecognitionCandidate],
    ) -> RecognitionDecision:
        if not candidates:
            return RecognitionDecision(
                status=RecognitionStatus.UNKNOWN,
                telemetry=RecognitionTelemetry(provider="openclip"),
            )

        fast_path_started_at = perf_counter()
        embedding_started_at = perf_counter()
        embedding = await self._embedder.embed(image_bytes)
        embedding_generation_ms = (perf_counter() - embedding_started_at) * 1000

        search_started_at = perf_counter()
        matches = self._searcher.search(
            embedding=embedding,
            candidate_product_ids=[candidate.product_id for candidate in candidates],
            limit=2,
        )
        vector_search_ms = (perf_counter() - search_started_at) * 1000

        top1_similarity, top2_similarity, margin = _similarity_stats(matches)
        fast_path_total_ms = (perf_counter() - fast_path_started_at) * 1000
        fast_path_matched = (
            bool(matches)
            and matches[0].product_id in {candidate.product_id for candidate in candidates}
            and top1_similarity is not None
            and top2_similarity is not None
            and top1_similarity >= self._match_threshold
            and margin is not None
            and margin >= self._margin_threshold
        )
        telemetry = RecognitionTelemetry(
            provider="openclip",
            embedding_generation_ms=embedding_generation_ms,
            vector_search_ms=vector_search_ms,
            fast_path_total_ms=fast_path_total_ms,
            top1_similarity=top1_similarity,
            top2_similarity=top2_similarity,
            similarity_margin=margin,
            fast_path_matched=fast_path_matched,
            openai_fallback=False,
        )

        if fast_path_matched:
            return RecognitionDecision(
                status=RecognitionStatus.MATCHED,
                product_id=matches[0].product_id,
                telemetry=telemetry,
            )

        if self._fallback is None:
            return RecognitionDecision(
                status=RecognitionStatus.UNKNOWN,
                telemetry=telemetry,
            )

        fallback_decision = await self._fallback.recognize(image_bytes, candidates)
        return replace(
            fallback_decision,
            telemetry=replace(telemetry, openai_fallback=True),
        )


def _similarity_stats(
    matches: list[ProductEmbeddingMatch],
) -> tuple[float | None, float | None, float | None]:
    if not matches:
        return None, None, None
    top1_similarity = matches[0].similarity
    top2_similarity = matches[1].similarity if len(matches) > 1 else None
    margin = top1_similarity - top2_similarity if top2_similarity is not None else None
    return top1_similarity, top2_similarity, margin
