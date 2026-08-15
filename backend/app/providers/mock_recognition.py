from dataclasses import dataclass

from app.domain.enums import RecognitionStatus


@dataclass(frozen=True, slots=True)
class RecognitionCandidate:
    product_id: str
    sku: str
    brand: str
    name: str
    category: str


@dataclass(frozen=True, slots=True)
class RecognitionDecision:
    status: RecognitionStatus
    product_id: str | None = None
    candidate_product_ids: tuple[str, ...] = ()


class MockRecognitionProviderError(Exception):
    pass


class MockRecognitionProvider:
    def __init__(
        self,
        *,
        status: RecognitionStatus = RecognitionStatus.MATCHED,
        product_id: str | None = None,
        should_fail: bool = False,
    ) -> None:
        self._status = status
        self._product_id = product_id
        self._should_fail = should_fail

    async def recognize(
        self,
        image_bytes: bytes,
        candidates: list[RecognitionCandidate],
    ) -> RecognitionDecision:
        if self._should_fail:
            raise MockRecognitionProviderError("Configured mock provider failure")

        if self._status is RecognitionStatus.UNKNOWN or not candidates:
            return RecognitionDecision(status=RecognitionStatus.UNKNOWN)

        if self._status is RecognitionStatus.AMBIGUOUS:
            candidate_ids = tuple(candidate.product_id for candidate in candidates[:2])
            return RecognitionDecision(
                status=RecognitionStatus.AMBIGUOUS,
                candidate_product_ids=candidate_ids,
            )

        product_id = self._product_id or candidates[0].product_id
        return RecognitionDecision(
            status=RecognitionStatus.MATCHED,
            product_id=product_id,
        )
