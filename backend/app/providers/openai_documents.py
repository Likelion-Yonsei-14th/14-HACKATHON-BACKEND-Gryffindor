import base64

from openai import AsyncOpenAI, OpenAIError
from openai.types.responses import ResponseInputParam
from pydantic import ValidationError

from app.providers.documents import (
    DocumentExtractionProviderError,
    FlightExtraction,
    ReceiptExtraction,
)


class OpenAIDocumentExtractionProvider:
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
        self._client = client or AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def extract_receipt(self, image_bytes: bytes) -> ReceiptExtraction:
        return await self._extract_receipt(image_bytes)

    async def extract_flight(self, image_bytes: bytes) -> FlightExtraction:
        return await self._extract_flight(image_bytes)

    async def _extract_receipt(self, image_bytes: bytes) -> ReceiptExtraction:
        try:
            response = await self._client.responses.parse(
                model=self._model,
                input=_image_input(_RECEIPT_PROMPT, image_bytes),
                text_format=ReceiptExtraction,
                reasoning={"effort": "none"},
            )
            return ReceiptExtraction.model_validate(response.output_parsed)
        except (OpenAIError, ValidationError) as exc:
            raise DocumentExtractionProviderError("Receipt extraction failed") from exc

    async def _extract_flight(self, image_bytes: bytes) -> FlightExtraction:
        try:
            response = await self._client.responses.parse(
                model=self._model,
                input=_image_input(_FLIGHT_PROMPT, image_bytes),
                text_format=FlightExtraction,
                reasoning={"effort": "none"},
            )
            return FlightExtraction.model_validate(response.output_parsed)
        except (OpenAIError, ValidationError) as exc:
            raise DocumentExtractionProviderError("Flight extraction failed") from exc


def _image_input(prompt: str, image_bytes: bytes) -> ResponseInputParam:
    media_type = _image_media_type(image_bytes)
    image_base64 = base64.b64encode(image_bytes).decode("ascii")
    return [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": prompt}],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Extract this document."},
                {
                    "type": "input_image",
                    "image_url": f"data:{media_type};base64,{image_base64}",
                    "detail": "high",
                },
            ],
        },
    ]


def _image_media_type(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    raise DocumentExtractionProviderError("Document input must be a JPEG or PNG image")


_RECEIPT_PROMPT = """Extract one shopping receipt into the provided schema. Use only facts visible
in the image. Return null for optional values that are absent or uncertain; never guess. Preserve
the item names as printed, use a three-letter uppercase currency code, integer minor-unit-free
amounts, and an ISO 8601 timestamp with an explicit timezone offset. Include every visible item.
"""

_FLIGHT_PROMPT = """Extract one flight ticket or boarding pass into the provided schema. Use only
facts visible in the image. Return null for optional values that are absent or uncertain; never
guess. Return IATA airports as uppercase three-letter codes and departureAt as ISO 8601 with an
explicit timezone offset. Do not infer a date or timezone that is not supported by the document.
"""
