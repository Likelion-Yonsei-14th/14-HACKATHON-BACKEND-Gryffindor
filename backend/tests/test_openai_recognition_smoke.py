import json
import os
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


@pytest.mark.openai_smoke
@pytest.mark.anyio
@pytest.mark.skipif(
    os.getenv("RUN_OPENAI_RECOGNITION_SMOKE") != "1",
    reason="Set RUN_OPENAI_RECOGNITION_SMOKE=1 to opt in to a real OpenAI request.",
)
async def test_real_openai_recognition_smoke() -> None:
    settings = Settings()
    assert settings.openai_api_key is not None, "OPENAI_API_KEY is required"

    image_path = Path(os.environ["OPENAI_RECOGNITION_SMOKE_IMAGE"])
    expected_status = RecognitionStatus(
        os.getenv("OPENAI_RECOGNITION_SMOKE_EXPECTED_STATUS", "MATCHED")
    )
    expected_product_id = os.getenv("OPENAI_RECOGNITION_SMOKE_EXPECTED_PRODUCT_ID")
    seed_path = Path(__file__).parents[1] / "data" / "products.seed.json"
    seed_products = cast(list[SeedProduct], json.loads(seed_path.read_text(encoding="utf-8")))
    candidates = [
        RecognitionCandidate(
            product_id=product["productId"],
            sku=product["sku"],
            brand=product["brand"],
            name=product["name"],
            category=product["category"],
        )
        for product in seed_products[: settings.recognition_max_candidates]
    ]
    provider = OpenAIRecognitionProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_vision_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )

    decision = await provider.recognize(image_path.read_bytes(), candidates)

    assert decision.status is expected_status
    if expected_product_id is not None:
        assert decision.product_id == expected_product_id
