from dataclasses import dataclass
from typing import Protocol

from app.domain.enums import RecognitionStatus


@dataclass(frozen=True, slots=True)
class RecognitionCandidate:
    product_id: str
    sku: str
    brand: str
    name: str
    category: str
    reference_image_url: str | None = None


@dataclass(frozen=True, slots=True)
class RecognitionTelemetry:
    provider: str
    embedding_generation_ms: float | None = None
    vector_search_ms: float | None = None
    fast_path_total_ms: float | None = None
    top1_similarity: float | None = None
    top2_similarity: float | None = None
    similarity_margin: float | None = None
    fast_path_matched: bool = False
    openai_fallback: bool = False


@dataclass(frozen=True, slots=True)
class RecognitionDecision:
    status: RecognitionStatus
    product_id: str | None = None
    candidate_product_ids: tuple[str, ...] = ()
    telemetry: RecognitionTelemetry | None = None


class RecognitionProviderError(Exception):
    """A retryable or malformed response from a recognition provider."""


class RecognitionProvider(Protocol):
    async def recognize(
        self,
        image_bytes: bytes,
        candidates: list[RecognitionCandidate],
    ) -> RecognitionDecision: ...
