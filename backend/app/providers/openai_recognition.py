import base64
import json

from openai import AsyncOpenAI, OpenAIError
from openai.types.responses import ResponseInputContentParam
from pydantic import BaseModel, ConfigDict, ValidationError

from app.domain.enums import RecognitionStatus
from app.providers.recognition import (
    RecognitionCandidate,
    RecognitionDecision,
    RecognitionProviderError,
)


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
                        "detail": "high",
                    },
                ]
            )
        user_content: list[ResponseInputContentParam] = [
            {
                "type": "input_text",
                "text": "Allowed catalog:\n" + json.dumps(catalog, ensure_ascii=False),
            },
            *reference_content,
            {
                "type": "input_text",
                "text": "Query image to identify against the references:",
            },
            {
                "type": "input_image",
                "image_url": f"data:{media_type};base64,{image_base64}",
                "detail": "high",
            },
        ]

        try:
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
            )
            output = OpenAIRecognitionOutput.model_validate(response.output_parsed)
        except (OpenAIError, ValidationError) as exc:
            raise RecognitionProviderError("OpenAI recognition request failed") from exc

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


_SYSTEM_PROMPT = """You identify the single product centered in a camera crop.
Compare the labeled catalog reference images and metadata with the final query image, and return the
required structured result using only the supplied allowed catalog.
Use MATCHED only when exactly one catalog product is sufficiently identifiable, and set product_id
to that allowed ID with an empty candidate_product_ids list. Use AMBIGUOUS when at least two allowed
catalog products remain plausible, set product_id to null, and list only those allowed IDs. Use
UNKNOWN for an unregistered product, a non-product image, or insufficient evidence, with product_id
set to null and an empty candidate_product_ids list. Never invent an ID or product.
"""
