from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from httpx import Request
from openai import APITimeoutError, AsyncOpenAI

from app.providers.documents import (
    DocumentExtractionProviderError,
    FlightExtraction,
    ReceiptExtraction,
    ReceiptItemExtraction,
)
from app.providers.openai_documents import OpenAIDocumentExtractionProvider
from app.providers.openai_recommendation import OpenAIRecommendationProvider
from app.providers.recommendation import (
    CandidateProductContext,
    CandidateStoreContext,
    RecommendationContext,
    RecommendationDecision,
    RecommendationProductDecision,
    RecommendationProviderError,
    RecommendationStoreDecision,
)


class FakeResponses:
    def __init__(self, output: object | None = None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_parsed=self.output)


class FakeOpenAIClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def document_provider_with(responses: FakeResponses) -> OpenAIDocumentExtractionProvider:
    return OpenAIDocumentExtractionProvider(
        api_key="test-key",
        model="test-document-model",
        timeout_seconds=1,
        client=cast(AsyncOpenAI, FakeOpenAIClient(responses)),
    )


def recommendation_provider_with(responses: FakeResponses) -> OpenAIRecommendationProvider:
    return OpenAIRecommendationProvider(
        api_key="test-key",
        model="test-recommendation-model",
        timeout_seconds=1,
        client=cast(AsyncOpenAI, FakeOpenAIClient(responses)),
    )


@pytest.mark.anyio
async def test_receipt_and_flight_use_one_structured_document_provider() -> None:
    receipt_output = ReceiptExtraction(
        store_name="Demo Store",
        purchased_at=datetime.fromisoformat("2026-08-19T14:30:00+09:00"),
        currency="KRW",
        total_amount=159_000,
        items=[ReceiptItemExtraction(name="Demo Jacket", quantity=1, price=159_000)],
    )
    receipt_responses = FakeResponses(receipt_output)
    receipt = await document_provider_with(receipt_responses).extract_receipt(b"\xff\xd8\xffimage")

    assert receipt == receipt_output
    receipt_call = receipt_responses.calls[0]
    assert receipt_call["model"] == "test-document-model"
    assert receipt_call["text_format"] is ReceiptExtraction
    assert receipt_call["reasoning"] == {"effort": "none"}
    assert receipt_call["input"][1]["content"][1]["detail"] == "high"

    flight_output = FlightExtraction(
        departure_airport="ICN",
        arrival_airport="JFK",
        flight_number="KE081",
        departure_at=datetime.fromisoformat("2026-08-21T10:00:00+09:00"),
    )
    flight_responses = FakeResponses(flight_output)
    flight = await document_provider_with(flight_responses).extract_flight(
        b"\x89PNG\r\n\x1a\nimage"
    )

    assert flight == flight_output
    assert flight_responses.calls[0]["text_format"] is FlightExtraction


@pytest.mark.anyio
@pytest.mark.parametrize("output", [None, {"storeName": "missing fields"}])
async def test_invalid_document_structured_output_is_provider_error(output: object | None) -> None:
    provider = document_provider_with(FakeResponses(output))

    with pytest.raises(DocumentExtractionProviderError):
        await provider.extract_receipt(b"\xff\xd8\xffimage")


@pytest.mark.anyio
async def test_invalid_flight_structured_output_is_provider_error() -> None:
    provider = document_provider_with(FakeResponses(None))

    with pytest.raises(DocumentExtractionProviderError):
        await provider.extract_flight(b"\xff\xd8\xffimage")


@pytest.mark.anyio
async def test_document_openai_failure_is_provider_error() -> None:
    timeout = APITimeoutError(request=Request("POST", "https://api.openai.com/v1/responses"))
    provider = document_provider_with(FakeResponses(error=timeout))

    with pytest.raises(DocumentExtractionProviderError):
        await provider.extract_flight(b"\xff\xd8\xffimage")


def _recommendation_context() -> RecommendationContext:
    store_id = UUID("10000000-0000-0000-0000-000000000003")
    return RecommendationContext(
        wishlist_product_ids=["demo_perfume_001"],
        viewed_products=[],
        purchased_product_ids=[],
        latest_flight=None,
        candidate_stores=[
            CandidateStoreContext(
                store_id=store_id,
                name="Airport Store",
                country="KR",
                city="Incheon",
                type="AIRPORT",
                airport_code="ICN",
                product_ids=["demo_perfume_001"],
            )
        ],
        candidate_products=[
            CandidateProductContext(
                product_id="demo_perfume_001",
                sku="SKU",
                brand="Brand",
                name="Perfume",
                category="perfume",
                store_ids=[store_id],
            )
        ],
    )


@pytest.mark.anyio
async def test_recommendation_provider_sends_allowlisted_context_as_structured_input() -> None:
    store_id = UUID("10000000-0000-0000-0000-000000000003")
    output = RecommendationDecision(
        stores=[
            RecommendationStoreDecision(
                store_id=store_id,
                reason="출국 전 방문하기 좋습니다.",
                products=[
                    RecommendationProductDecision(
                        product_id="demo_perfume_001",
                        reason="Wishlist에 저장한 상품입니다.",
                    )
                ],
            )
        ]
    )
    responses = FakeResponses(output)

    decision = await recommendation_provider_with(responses).recommend(_recommendation_context())

    assert decision == output
    call = responses.calls[0]
    assert call["model"] == "test-recommendation-model"
    assert call["text_format"] is RecommendationDecision
    assert '"candidateStores"' in call["input"][1]["content"][0]["text"]
    assert '"demo_perfume_001"' in call["input"][1]["content"][0]["text"]


@pytest.mark.anyio
async def test_invalid_recommendation_structured_output_is_provider_error() -> None:
    provider = recommendation_provider_with(FakeResponses(None))

    with pytest.raises(RecommendationProviderError):
        await provider.recommend(_recommendation_context())
