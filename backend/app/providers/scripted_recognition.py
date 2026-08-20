from app.domain.enums import RecognitionStatus
from app.providers.recognition import (
    RecognitionCandidate,
    RecognitionDecision,
    RecognitionProviderError,
)


class ScriptedRecognitionProviderError(RecognitionProviderError):
    pass


class ScriptedRecognitionProvider:
    """Return a configured recognition decision without inspecting the image."""

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
        del image_bytes
        if self._should_fail:
            raise ScriptedRecognitionProviderError("Configured recognition provider failure")

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
