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


_SYSTEM_PROMPT = """You are a personalized shopping recommendation engine.

Use wishlist, smart-glasses viewed products, purchase history, flight/travel schedule,
candidateStores, and candidateProducts. Recommend only storeId and productId values explicitly
included in candidateStores and candidateProducts. Every recommended product must list the
returned storeId in its storeIds and in that candidate store's productIds.

Never invent a store, product, storeId, or productId. Prioritize: (1) strong wishlist matches,
(2) repeatedly viewed but not purchased products, (3) observed preferences, (4) travel and airport
convenience, and (5) avoiding already purchased products. Unmatched purchased product names and
store names describe user taste only and never authorize a new productId. Produce concise
personalized Korean reasons for every store and product. Return the provided structured output only.
"""
