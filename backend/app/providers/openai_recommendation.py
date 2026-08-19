import json

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from app.providers.recommendation import (
    RecommendationContext,
    RecommendationDecision,
    RecommendationProviderError,
)


class OpenAIRecommendationProvider:
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

    async def recommend(self, context: RecommendationContext) -> RecommendationDecision:
        context_json = json.dumps(
            context.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            response = await self._client.responses.parse(
                model=self._model,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": _SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "Recommendation context:\n" + context_json,
                            }
                        ],
                    },
                ],
                text_format=RecommendationDecision,
                reasoning={"effort": "none"},
            )
            return RecommendationDecision.model_validate(response.output_parsed)
        except (OpenAIError, ValidationError) as exc:
            raise RecommendationProviderError("OpenAI recommendation failed") from exc


_SYSTEM_PROMPT = """You are a personalized luxury shopping recommendation engine.

The user may be planning a specific trip. Use trip, wishlist, smart-glasses viewed products,
purchased products, hotel location, flight schedule, candidate stores, candidate products,
distance from hotel, and airport/terminal match information. The server has already calculated
distance, database existence, inventory relationships, and airport matches. Do not recalculate or
invent those facts.

Recommend only storeId and productId values explicitly included in candidateStores and
candidateProducts. Every recommended product must list the returned storeId in its storeIds and in
that candidate store's productIds. Never invent a Store/Product ID.

Prefer: (1) explicitly wishlisted products, (2) products strongly related to viewed behavior,
(3) products not already purchased, (4) stores close to the hotel, (5) departure-airport stores
when relevant, and (6) stores that actually carry the recommended products. Unmatched purchased
product names and store names describe taste only and never authorize a new productId. Generate
concise Korean personalized reasons for every store and product. Return the structured output only.
"""
