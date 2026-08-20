import logging
from types import SimpleNamespace
from typing import Any, cast

import pytest
from httpx import Request
from openai import APITimeoutError, AsyncOpenAI

from app.domain.enums import RecognitionStatus
from app.providers.openai_recognition import (
    OpenAIRecognitionOutput,
    OpenAIRecognitionProvider,
)
from app.providers.recognition import RecognitionCandidate, RecognitionProviderError


class ScriptedResponses:
    def __init__(
        self,
        output: OpenAIRecognitionOutput | None = None,
        error: Exception | None = None,
    ) -> None:
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


@pytest.fixture
def candidates() -> list[RecognitionCandidate]:
    return [
        RecognitionCandidate(
            "catalog_001",
            "SKU001",
            "Brand A",
            "Jacket A",
            "jacket",
            reference_image_url="data:image/jpeg;base64,cmVmMQ==",
        ),
        RecognitionCandidate(
            "catalog_002",
            "SKU002",
            "Brand B",
            "Jacket B",
            "jacket",
            reference_image_url="data:image/jpeg;base64,cmVmMg==",
        ),
    ]


def provider_with(responses: ScriptedResponses) -> OpenAIRecognitionProvider:
    return OpenAIRecognitionProvider(
        api_key="test-key",
        model="test-model",
        timeout_seconds=1,
        client=cast(AsyncOpenAI, RecordingOpenAIClient(responses)),
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("output", "expected_status", "expected_product_id", "expected_candidates"),
    [
        (
            OpenAIRecognitionOutput(
                status=RecognitionStatus.MATCHED,
                product_id="catalog_001",
                candidate_product_ids=[],
            ),
            RecognitionStatus.MATCHED,
            "catalog_001",
            (),
        ),
        (
            OpenAIRecognitionOutput(
                status=RecognitionStatus.AMBIGUOUS,
                product_id=None,
                candidate_product_ids=["catalog_001", "catalog_002"],
            ),
            RecognitionStatus.AMBIGUOUS,
            None,
            ("catalog_001", "catalog_002"),
        ),
        (
            OpenAIRecognitionOutput(
                status=RecognitionStatus.UNKNOWN,
                product_id=None,
                candidate_product_ids=[],
            ),
            RecognitionStatus.UNKNOWN,
            None,
            (),
        ),
    ],
)
async def test_structured_results_map_to_common_decision(
    candidates: list[RecognitionCandidate],
    output: OpenAIRecognitionOutput,
    expected_status: RecognitionStatus,
    expected_product_id: str | None,
    expected_candidates: tuple[str, ...],
) -> None:
    scripted_responses = ScriptedResponses(output=output)

    decision = await provider_with(scripted_responses).recognize(
        b"\xff\xd8\xffimage",
        candidates,
    )

    assert decision.status is expected_status
    assert decision.product_id == expected_product_id
    assert decision.candidate_product_ids == expected_candidates

    request = scripted_responses.calls[0]
    assert request["model"] == "test-model"
    assert request["text_format"] is OpenAIRecognitionOutput
    assert request["reasoning"] == {"effort": "none"}
    user_content = request["input"][1]["content"]
    assert user_content[0]["type"] == "input_text"
    assert '"product_id":"catalog_001"' in user_content[0]["text"]
    image_content = [content for content in user_content if content["type"] == "input_image"]
    assert [content["image_url"] for content in image_content[:2]] == [
        "data:image/jpeg;base64,cmVmMQ==",
        "data:image/jpeg;base64,cmVmMg==",
    ]
    assert image_content[2]["image_url"].startswith("data:image/jpeg;base64,")
    assert {content["detail"] for content in image_content} == {"low"}


@pytest.mark.anyio
async def test_empty_catalog_returns_unknown_without_openai_call() -> None:
    scripted_responses = ScriptedResponses()

    decision = await provider_with(scripted_responses).recognize(b"image", [])

    assert decision.status is RecognitionStatus.UNKNOWN
    assert scripted_responses.calls == []


@pytest.mark.anyio
async def test_timeout_is_mapped_to_common_provider_error(
    candidates: list[RecognitionCandidate],
) -> None:
    timeout = APITimeoutError(request=Request("POST", "https://api.openai.com/v1/responses"))
    provider = provider_with(ScriptedResponses(error=timeout))

    with pytest.raises(RecognitionProviderError):
        await provider.recognize(b"\x89PNG\r\n\x1a\nimage", candidates)


@pytest.mark.anyio
async def test_missing_structured_output_is_provider_error(
    candidates: list[RecognitionCandidate],
) -> None:
    provider = provider_with(ScriptedResponses(output=None))

    with pytest.raises(RecognitionProviderError):
        await provider.recognize(b"\xff\xd8\xffimage", candidates)


@pytest.mark.anyio
async def test_success_logs_openai_latency(
    candidates: list[RecognitionCandidate],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.providers.openai_recognition")
    provider = provider_with(
        ScriptedResponses(
            output=OpenAIRecognitionOutput(
                status=RecognitionStatus.MATCHED,
                product_id="catalog_001",
                candidate_product_ids=[],
            )
        )
    )

    await provider.recognize(b"\xff\xd8\xffimage", candidates)

    messages = [record.getMessage() for record in caplog.records]
    assert any(message.startswith("OpenAI recognition start ") for message in messages)
    completed = next(
        message for message in messages if message.startswith("OpenAI recognition completed ")
    )
    for expected_part in (
        "elapsedMs=",
        "result=MATCHED",
        "prepareMs=",
        "apiCallMs=",
        "parseMs=",
    ):
        assert expected_part in completed
