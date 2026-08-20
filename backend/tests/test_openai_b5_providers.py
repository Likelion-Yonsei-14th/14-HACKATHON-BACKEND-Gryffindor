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


class ScriptedResponses:
    def __init__(self, output: object | None = None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_parsed=self.output)


class RecordingOpenAIClient:
    def __init__(self, responses: ScriptedResponses) -> None:
        self.responses = responses


def document_provider_with(responses: ScriptedResponses) -> OpenAIDocumentExtractionProvider:
    return OpenAIDocumentExtractionProvider(
        api_key="test-key",
        model="test-document-model",
        timeout_seconds=1,
        client=cast(AsyncOpenAI, RecordingOpenAIClient(responses)),
    )


def recommendation_provider_with(responses: ScriptedResponses) -> OpenAIRecommendationProvider:
    return OpenAIRecommendationProvider(
        api_key="test-key",
        model="test-recommendation-model",
        timeout_seconds=1,
        client=cast(AsyncOpenAI, RecordingOpenAIClient(responses)),
    )


@pytest.mark.anyio
async def test_receipt_and_flight_use_one_structured_document_provider() -> None:
    receipt_output = ReceiptExtraction(
        store_name="Reference Store",
        purchased_at=datetime.fromisoformat("2026-08-19T14:30:00+09:00"),
        currency="KRW",
        total_amount=159_000,
        items=[ReceiptItemExtraction(name="Reference Jacket", quantity=1, price=159_000)],
    )
    receipt_responses = ScriptedResponses(receipt_output)
    receipt = await document_provider_with(receipt_responses).extract_receipt(b"\xff\xd8\xffimage")

    assert receipt == receipt_output
    receipt_call = receipt_responses.calls[0]
    assert receipt_call["model"] == "test-document-model"
    assert receipt_call["text_format"] is ReceiptExtraction
    assert receipt_call["reasoning"] == {"effort": "none"}
    assert receipt_call["input"][1]["content"][1]["detail"] == "high"
    receipt_prompt = receipt_call["input"][0]["content"][0]["text"]
    assert "Do not correct or reconcile" in receipt_prompt
    assert "refund-processing information" in receipt_prompt

    flight_output = FlightExtraction(
        departure_airport="ICN",
        arrival_airport="JFK",
        terminal="T2",
        flight_number="KE081",
        departure_at=datetime.fromisoformat("2026-08-21T10:00:00+09:00"),
        arrival_at=datetime.fromisoformat("2026-08-21T11:00:00-04:00"),
    )
    flight_responses = ScriptedResponses(flight_output)
    flight = await document_provider_with(flight_responses).extract_flight(
        b"\x89PNG\r\n\x1a\nimage"
    )

    assert flight == flight_output
    assert flight_responses.calls[0]["text_format"] is FlightExtraction
    flight_prompt = flight_responses.calls[0]["input"][0]["content"][0]["text"]
    assert "airport arrival" in flight_prompt


@pytest.mark.anyio
@pytest.mark.parametrize("output", [None, {"storeName": "missing fields"}])
async def test_invalid_document_structured_output_is_provider_error(output: object | None) -> None:
    provider = document_provider_with(ScriptedResponses(output))

    with pytest.raises(DocumentExtractionProviderError):
        await provider.extract_receipt(b"\xff\xd8\xffimage")


@pytest.mark.anyio
async def test_invalid_flight_structured_output_is_provider_error() -> None:
    provider = document_provider_with(ScriptedResponses(None))

    with pytest.raises(DocumentExtractionProviderError):
        await provider.extract_flight(b"\xff\xd8\xffimage")


@pytest.mark.anyio
async def test_document_openai_failure_is_provider_error() -> None:
    timeout = APITimeoutError(request=Request("POST", "https://api.openai.com/v1/responses"))
    provider = document_provider_with(ScriptedResponses(error=timeout))

    with pytest.raises(DocumentExtractionProviderError):
        await provider.extract_flight(b"\xff\xd8\xffimage")


def _recommendation_context() -> RecommendationContext:
    store_id = UUID("10000000-0000-0000-0000-000000000003")
    return RecommendationContext(
        wishlist_product_ids=["anillo_fragrance_of_life_10_001"],
        viewed_products=[],
        purchased_product_ids=[],
        purchased_products=[],
        latest_flight=None,
        candidate_stores=[
            CandidateStoreContext(
                store_id=store_id,
                name="Airport Store",
                country="KR",
                city="Incheon",
                type="AIRPORT",
                airport_code="ICN",
                product_ids=["anillo_fragrance_of_life_10_001"],
            )
        ],
        candidate_products=[
            CandidateProductContext(
                product_id="anillo_fragrance_of_life_10_001",
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
                        product_id="anillo_fragrance_of_life_10_001",
                        reason="Wishlist에 저장한 상품입니다.",
                    )
                ],
            )
        ]
    )
    responses = ScriptedResponses(output)

    decision = await recommendation_provider_with(responses).recommend(_recommendation_context())

    assert decision == output
    call = responses.calls[0]
    assert call["model"] == "test-recommendation-model"
    assert call["text_format"] is RecommendationDecision
    assert '"candidateStores"' in call["input"][1]["content"][0]["text"]
    assert '"anillo_fragrance_of_life_10_001"' in call["input"][1]["content"][0]["text"]


@pytest.mark.anyio
async def test_invalid_recommendation_structured_output_is_provider_error() -> None:
    provider = recommendation_provider_with(ScriptedResponses(None))

    with pytest.raises(RecommendationProviderError):
        await provider.recommend(_recommendation_context())
