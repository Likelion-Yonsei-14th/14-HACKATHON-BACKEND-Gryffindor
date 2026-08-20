from dataclasses import dataclass

import pytest

from app.domain.enums import RecognitionStatus
from app.providers.openclip_recognition import OpenCLIPRecognitionProvider
from app.providers.recognition import RecognitionCandidate, RecognitionDecision
from app.repositories.product_embeddings import ProductEmbeddingMatch


@dataclass
class StaticEmbedder:
    embedding: list[float]

    async def embed(self, image_bytes: bytes) -> list[float]:
        del image_bytes
        return self.embedding


class StaticSearcher:
    def __init__(self, matches: list[ProductEmbeddingMatch]) -> None:
        self.matches = matches
        self.calls: list[dict[str, object]] = []

    def search(
        self,
        *,
        embedding: list[float],
        candidate_product_ids: list[str],
        limit: int = 2,
    ) -> list[ProductEmbeddingMatch]:
        self.calls.append(
            {
                "embedding": embedding,
                "candidate_product_ids": candidate_product_ids,
                "limit": limit,
            }
        )
        return self.matches


class RecordingFallbackProvider:
    def __init__(self, decision: RecognitionDecision) -> None:
        self.decision = decision
        self.calls = 0

    async def recognize(
        self,
        image_bytes: bytes,
        candidates: list[RecognitionCandidate],
    ) -> RecognitionDecision:
        del image_bytes, candidates
        self.calls += 1
        return self.decision


def candidates() -> list[RecognitionCandidate]:
    return [
        RecognitionCandidate("dashu_aqua_dive_50_001", "mouse", "Logitech", "M185", "mouse"),
        RecognitionCandidate(
            "diptyque_leau_papier_100_001", "lotion", "BRINGGREEN", "Cream", "lotion"
        ),
        RecognitionCandidate(
            "anillo_fragrance_of_life_10_001", "perfume", "Diptyque", "Papier", "perfume"
        ),
    ]


@pytest.mark.anyio
async def test_confident_openclip_match_skips_openai_fallback() -> None:
    fallback = RecordingFallbackProvider(RecognitionDecision(status=RecognitionStatus.UNKNOWN))
    provider = OpenCLIPRecognitionProvider(
        embedder=StaticEmbedder([0.1, 0.2]),
        searcher=StaticSearcher(
            [
                ProductEmbeddingMatch("dashu_aqua_dive_50_001", 0.08),
                ProductEmbeddingMatch("diptyque_leau_papier_100_001", 0.30),
            ]
        ),
        fallback=fallback,
        match_threshold=0.80,
        margin_threshold=0.10,
    )

    decision = await provider.recognize(b"query", candidates())

    assert decision.status is RecognitionStatus.MATCHED
    assert decision.product_id == "dashu_aqua_dive_50_001"
    assert fallback.calls == 0
    assert decision.telemetry is not None
    assert decision.telemetry.provider == "openclip"
    assert abs((decision.telemetry.top1_similarity or 0) - 0.92) < 1e-9
    assert abs((decision.telemetry.top2_similarity or 0) - 0.70) < 1e-9
    assert abs((decision.telemetry.similarity_margin or 0) - 0.22) < 1e-9
    assert decision.telemetry.fast_path_matched is True
    assert decision.telemetry.openai_fallback is False


@pytest.mark.anyio
async def test_uncertain_openclip_result_uses_openai_fallback() -> None:
    fallback = RecordingFallbackProvider(
        RecognitionDecision(
            status=RecognitionStatus.MATCHED,
            product_id="dashu_aqua_dive_50_001",
        )
    )
    provider = OpenCLIPRecognitionProvider(
        embedder=StaticEmbedder([0.1, 0.2]),
        searcher=StaticSearcher(
            [
                ProductEmbeddingMatch("dashu_aqua_dive_50_001", 0.18),
                ProductEmbeddingMatch("diptyque_leau_papier_100_001", 0.20),
            ]
        ),
        fallback=fallback,
        match_threshold=0.80,
        margin_threshold=0.05,
    )

    decision = await provider.recognize(b"query", candidates())

    assert decision.status is RecognitionStatus.MATCHED
    assert decision.product_id == "dashu_aqua_dive_50_001"
    assert fallback.calls == 1
    assert decision.telemetry is not None
    assert abs((decision.telemetry.top1_similarity or 0) - 0.82) < 1e-9
    assert abs((decision.telemetry.top2_similarity or 0) - 0.80) < 1e-9
    assert abs((decision.telemetry.similarity_margin or 0) - 0.02) < 1e-9
    assert decision.telemetry.fast_path_matched is False
    assert decision.telemetry.openai_fallback is True


@pytest.mark.anyio
async def test_uncertain_openclip_result_without_fallback_is_unknown() -> None:
    provider = OpenCLIPRecognitionProvider(
        embedder=StaticEmbedder([0.1, 0.2]),
        searcher=StaticSearcher(
            [
                ProductEmbeddingMatch("dashu_aqua_dive_50_001", 0.18),
                ProductEmbeddingMatch("diptyque_leau_papier_100_001", 0.20),
            ]
        ),
        match_threshold=0.80,
        margin_threshold=0.05,
    )

    decision = await provider.recognize(b"query", candidates())

    assert decision.status is RecognitionStatus.UNKNOWN
    assert decision.telemetry is not None
    assert decision.telemetry.fast_path_matched is False
    assert decision.telemetry.openai_fallback is False


@pytest.mark.anyio
async def test_missing_top2_is_conservative_and_falls_back() -> None:
    fallback = RecordingFallbackProvider(RecognitionDecision(status=RecognitionStatus.UNKNOWN))
    provider = OpenCLIPRecognitionProvider(
        embedder=StaticEmbedder([0.1, 0.2]),
        searcher=StaticSearcher([ProductEmbeddingMatch("dashu_aqua_dive_50_001", 0.01)]),
        fallback=fallback,
        match_threshold=0.50,
        margin_threshold=0.01,
    )

    decision = await provider.recognize(b"query", candidates())

    assert decision.status is RecognitionStatus.UNKNOWN
    assert fallback.calls == 1
    assert decision.telemetry is not None
    assert decision.telemetry.top2_similarity is None
