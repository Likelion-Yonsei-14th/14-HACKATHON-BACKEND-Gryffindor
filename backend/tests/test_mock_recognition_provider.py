import pytest

from app.domain.enums import RecognitionStatus
from app.providers.mock_recognition import (
    MockRecognitionProvider,
    MockRecognitionProviderError,
    RecognitionCandidate,
)


@pytest.fixture
def candidates() -> list[RecognitionCandidate]:
    return [
        RecognitionCandidate("catalog_001", "SKU001", "Brand A", "Jacket A", "jacket"),
        RecognitionCandidate("catalog_002", "SKU002", "Brand B", "Jacket B", "jacket"),
    ]


@pytest.mark.anyio
async def test_mock_provider_returns_configured_match(
    candidates: list[RecognitionCandidate],
) -> None:
    provider = MockRecognitionProvider(product_id="catalog_002")

    decision = await provider.recognize(b"image", candidates)

    assert decision.status is RecognitionStatus.MATCHED
    assert decision.product_id == "catalog_002"


@pytest.mark.anyio
async def test_mock_provider_returns_ambiguous_candidates(
    candidates: list[RecognitionCandidate],
) -> None:
    provider = MockRecognitionProvider(status=RecognitionStatus.AMBIGUOUS)

    decision = await provider.recognize(b"image", candidates)

    assert decision.status is RecognitionStatus.AMBIGUOUS
    assert decision.candidate_product_ids == ("catalog_001", "catalog_002")


@pytest.mark.anyio
async def test_mock_provider_returns_unknown(candidates: list[RecognitionCandidate]) -> None:
    provider = MockRecognitionProvider(status=RecognitionStatus.UNKNOWN)

    decision = await provider.recognize(b"image", candidates)

    assert decision.status is RecognitionStatus.UNKNOWN
    assert decision.product_id is None


@pytest.mark.anyio
async def test_mock_provider_can_simulate_failure(
    candidates: list[RecognitionCandidate],
) -> None:
    provider = MockRecognitionProvider(should_fail=True)

    with pytest.raises(MockRecognitionProviderError):
        await provider.recognize(b"image", candidates)
