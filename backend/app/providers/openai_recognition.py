import base64
import json
import logging
from time import perf_counter

from openai import AsyncOpenAI, OpenAIError
from openai.types.responses import ResponseInputContentParam
from pydantic import BaseModel, ConfigDict, ValidationError

from app.domain.enums import RecognitionStatus
from app.providers.recognition import (
    RecognitionCandidate,
    RecognitionDecision,
    RecognitionProviderError,
)

logger = logging.getLogger(__name__)


class OpenAIRecognitionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RecognitionStatus
    product_id: str | None
    candidate_product_ids: list[str]


class OpenAIRecognitionProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        self._owns_client = client is None
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def recognize(
        self,
        image_bytes: bytes,
        candidates: list[RecognitionCandidate],
    ) -> RecognitionDecision:
        if not candidates:
            return RecognitionDecision(status=RecognitionStatus.UNKNOWN)

        total_started_at = perf_counter()
        logger.info(
            "OpenAI recognition start model=%s candidates=%d imageBytes=%d",
            self._model,
            len(candidates),
            len(image_bytes),
        )
        prepare_started_at = perf_counter()
        media_type = _image_media_type(image_bytes)
        image_base64 = base64.b64encode(image_bytes).decode("ascii")
        catalog = [
            {
                "product_id": candidate.product_id,
                "sku": candidate.sku,
                "brand": candidate.brand,
                "name": candidate.name,
                "category": candidate.category,
            }
            for candidate in candidates
        ]
        reference_content: list[ResponseInputContentParam] = []
        for candidate in candidates:
            if candidate.reference_image_url is None:
                continue
            reference_content.extend(
                [
                    {
                        "type": "input_text",
                        "text": f"Reference image for product_id={candidate.product_id}:",
                    },
                    {
                        "type": "input_image",
                        "image_url": candidate.reference_image_url,
                        "detail": "low",
                    },
                ]
            )
        user_content: list[ResponseInputContentParam] = [
            {
                "type": "input_text",
                "text": "Allowed catalog:\n"
                + json.dumps(catalog, ensure_ascii=False, separators=(",", ":")),
            },
            *reference_content,
            {
                "type": "input_text",
                "text": "Query image:",
            },
            {
                "type": "input_image",
                "image_url": f"data:{media_type};base64,{image_base64}",
                "detail": "low",
            },
        ]
        prepare_ms = (perf_counter() - prepare_started_at) * 1000

        try:
            api_call_started_at = perf_counter()
            response = await self._client.responses.parse(
                model=self._model,
                input=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": _SYSTEM_PROMPT,
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ],
                text_format=OpenAIRecognitionOutput,
                reasoning={"effort": "none"},
            )
            api_call_ms = (perf_counter() - api_call_started_at) * 1000
            parse_started_at = perf_counter()
            output = OpenAIRecognitionOutput.model_validate(response.output_parsed)
            parse_ms = (perf_counter() - parse_started_at) * 1000
        except (OpenAIError, ValidationError) as exc:
            raise RecognitionProviderError("OpenAI recognition request failed") from exc

        logger.info(
            "OpenAI recognition completed elapsedMs=%.2f result=%s "
            "prepareMs=%.2f apiCallMs=%.2f parseMs=%.2f",
            (perf_counter() - total_started_at) * 1000,
            output.status,
            prepare_ms,
            api_call_ms,
            parse_ms,
        )
        return RecognitionDecision(
            status=output.status,
            product_id=output.product_id,
            candidate_product_ids=tuple(output.candidate_product_ids),
        )


def _image_media_type(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    raise RecognitionProviderError("Recognition input must be a JPEG or PNG image")


_SYSTEM_PROMPT = """Identify the single centered product by comparing the query image with labeled
catalog references and metadata. Return only the structured result using the allowed catalog.
MATCHED: exactly one sufficiently identifiable product; product_id=its allowed ID;
candidate_product_ids=[]. AMBIGUOUS: at least two allowed products remain plausible;
product_id=null; candidate_product_ids=their allowed IDs. UNKNOWN: unregistered product,
non-product, or insufficient evidence; product_id=null; candidate_product_ids=[]. Never invent a
product or ID.
"""
