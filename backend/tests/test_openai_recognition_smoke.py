import base64
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TypedDict, cast

import pytest

from app.core.config import Settings
from app.domain.enums import RecognitionStatus
from app.providers.openai_recognition import OpenAIRecognitionProvider
from app.providers.recognition import RecognitionCandidate


class SeedProduct(TypedDict):
    productId: str
    sku: str
    brand: str
    name: str
    category: str


_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "openai"
_REFERENCE_PRODUCT_IDS = (
    "demo_lotion_001",
    "demo_mouse_001",
    "demo_perfume_001",
)


pytestmark = [
    pytest.mark.openai_smoke,
    pytest.mark.skipif(
        os.getenv("RUN_OPENAI_RECOGNITION_SMOKE") != "1",
        reason="Set RUN_OPENAI_RECOGNITION_SMOKE=1 to opt in to real OpenAI requests.",
    ),
]


def _provider_and_candidates() -> tuple[OpenAIRecognitionProvider, list[RecognitionCandidate]]:
    settings = Settings()
    assert settings.openai_api_key is not None, "OPENAI_API_KEY is required"

    seed_path = Path(__file__).parents[1] / "data" / "products.seed.json"
    seed_products = cast(list[SeedProduct], json.loads(seed_path.read_text(encoding="utf-8")))
    products_by_id = {product["productId"]: product for product in seed_products}
    candidates = [
        RecognitionCandidate(
            product_id=product_id,
            sku=products_by_id[product_id]["sku"],
            brand=products_by_id[product_id]["brand"],
            name=products_by_id[product_id]["name"],
            category=products_by_id[product_id]["category"],
            reference_image_url=_jpeg_data_url(_FIXTURE_ROOT / f"{product_id}_ref.jpg"),
        )
        for product_id in _REFERENCE_PRODUCT_IDS
    ]
    provider = OpenAIRecognitionProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_vision_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    return provider, candidates


@pytest.fixture
async def openai_provider_and_candidates(
    anyio_backend: object,
) -> AsyncIterator[tuple[OpenAIRecognitionProvider, list[RecognitionCandidate]]]:
    provider_and_candidates = _provider_and_candidates()
    try:
        yield provider_and_candidates
    finally:
        await provider_and_candidates[0].close()


@pytest.mark.anyio
@pytest.mark.parametrize("product_id", _REFERENCE_PRODUCT_IDS)
async def test_real_openai_matches_a4_demo_catalog(
    product_id: str,
    openai_provider_and_candidates: tuple[OpenAIRecognitionProvider, list[RecognitionCandidate]],
) -> None:
    provider, candidates = openai_provider_and_candidates

    decision = await provider.recognize(
        _jpeg_bytes(_FIXTURE_ROOT / "query" / f"{product_id}_query.jpg"),
        candidates,
    )

    assert decision.status is RecognitionStatus.MATCHED
    assert decision.product_id == product_id


@pytest.mark.anyio
async def test_real_openai_returns_unknown_for_unrelated_query(
    openai_provider_and_candidates: tuple[OpenAIRecognitionProvider, list[RecognitionCandidate]],
) -> None:
    provider, candidates = openai_provider_and_candidates

    decision = await provider.recognize(
        _jpeg_bytes(_FIXTURE_ROOT / "query" / "unrelated.jpg"),
        candidates,
    )

    assert decision.status is RecognitionStatus.UNKNOWN
    assert decision.product_id is None


def _jpeg_data_url(path: Path) -> str:
    image_bytes = _jpeg_bytes(path)
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")


def _jpeg_bytes(path: Path) -> bytes:
    assert path.is_file(), f"Smoke fixture is missing: {path}"
    image_bytes = path.read_bytes()
    assert image_bytes.startswith(b"\xff\xd8\xff"), f"Fixture must be JPEG: {path}"
    return image_bytes
