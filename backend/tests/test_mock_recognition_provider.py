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
        RecognitionCandidate("mcm_001", "SKU001", "MCM", "Bag", "bag"),
        RecognitionCandidate("mcm_002", "SKU002", "MCM", "Wallet", "wallet"),
    ]


@pytest.mark.anyio
async def test_mock_provider_returns_configured_match(
    candidates: list[RecognitionCandidate],
) -> None:
    provider = MockRecognitionProvider(product_id="mcm_002")

    decision = await provider.recognize(b"image", candidates)

    assert decision.status is RecognitionStatus.MATCHED
    assert decision.product_id == "mcm_002"


@pytest.mark.anyio
async def test_mock_provider_returns_ambiguous_candidates(
    candidates: list[RecognitionCandidate],
) -> None:
    provider = MockRecognitionProvider(status=RecognitionStatus.AMBIGUOUS)

    decision = await provider.recognize(b"image", candidates)

    assert decision.status is RecognitionStatus.AMBIGUOUS
    assert decision.candidate_product_ids == ("mcm_001", "mcm_002")


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
