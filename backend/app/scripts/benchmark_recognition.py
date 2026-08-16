from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path
from time import perf_counter

from app.core.config import Settings
from app.db.session import SessionLocal
from app.domain.enums import RecognitionStatus
from app.providers.openai_recognition import OpenAIRecognitionProvider
from app.providers.openclip_embedding import OpenCLIPImageEmbedder
from app.providers.openclip_recognition import OpenCLIPRecognitionProvider
from app.providers.recognition import RecognitionCandidate, RecognitionDecision, RecognitionProvider
from app.repositories.product_embeddings import ProductEmbeddingRepository
from app.repositories.products import ProductRepository

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "openai"
PRODUCT_IDS = ("demo_lotion_001", "demo_mouse_001", "demo_perfume_001")
QUERY_FIXTURES = {
    "demo_lotion_001": (
        "demo_lotion_001_query.jpg",
        "lotion_01.jpeg",
        "lotion_02.jpeg",
        "lotion_03.jpeg",
    ),
    "demo_mouse_001": (
        "demo_mouse_001_query.jpg",
        "Mouse_01.jpeg",
        "Mouse_02.jpeg",
        "Mouse_03.jpeg",
    ),
    "demo_perfume_001": (
        "demo_perfume_001_query.jpg",
        "perfume_01.jpeg",
        "perfume_02.jpeg",
        "perfume_03.jpeg",
    ),
}


class NoopFallback:
    async def recognize(
        self,
        image_bytes: bytes,
        candidates: list[RecognitionCandidate],
    ) -> RecognitionDecision:
        del image_bytes, candidates
        return RecognitionDecision(status=RecognitionStatus.UNKNOWN)


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Benchmark OpenCLIP recognition paths.")
    parser.add_argument("--run-openai", action="store_true", help="Measure real OpenAI calls.")
    parser.add_argument(
        "--all-query-fixtures",
        action="store_true",
        help="Measure all available per-product query fixtures.",
    )
    parser.add_argument(
        "--include-unrelated",
        action="store_true",
        help="Include the unrelated negative fixture in the fast-path distribution.",
    )
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be positive")

    with SessionLocal() as db:
        products = ProductRepository(db)
        catalog = [products.get_by_product_id(product_id) for product_id in PRODUCT_IDS]
        if any(product is None for product in catalog):
            raise SystemExit("All three demo products must be seeded before benchmarking.")
        concrete_products = [product for product in catalog if product is not None]
        candidates = [
            RecognitionCandidate(
                product_id=product.product_id,
                sku=product.sku,
                brand=product.brand,
                name=product.name,
                category=product.category,
                reference_image_url=_jpeg_data_url(FIXTURE_ROOT / f"{product.product_id}_ref.jpg"),
            )
            for product in concrete_products
        ]
        embedder = OpenCLIPImageEmbedder(
            model_name=settings.openclip_model,
            pretrained=settings.openclip_pretrained,
            device=settings.openclip_device,
            expected_dimension=settings.openclip_embedding_dimension,
        )
        fallback: RecognitionProvider
        openai_provider: OpenAIRecognitionProvider | None = None
        if args.run_openai:
            if settings.openai_api_key is None:
                raise SystemExit("OPENAI_API_KEY is required with --run-openai")
            openai_provider = OpenAIRecognitionProvider(
                api_key=settings.openai_api_key.get_secret_value(),
                model=settings.openai_vision_model,
                timeout_seconds=settings.openai_timeout_seconds,
            )
            fallback = openai_provider
        else:
            fallback = NoopFallback()

        fast_provider = OpenCLIPRecognitionProvider(
            embedder=embedder,
            searcher=ProductEmbeddingRepository(db),
            fallback=fallback,
            match_threshold=settings.openclip_match_threshold,
            margin_threshold=settings.openclip_margin_threshold,
        )
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        try:
            queries = [
                (product_id, filename)
                for product_id in PRODUCT_IDS
                for filename in (
                    QUERY_FIXTURES[product_id]
                    if args.all_query_fixtures
                    else QUERY_FIXTURES[product_id][:1]
                )
            ]
            if args.include_unrelated:
                queries.append(("unrelated", "unrelated.jpg"))
            warmup_product_id, warmup_filename = queries[0]
            warmup_started_at = perf_counter()
            _run(
                event_loop,
                fast_provider,
                (FIXTURE_ROOT / "query" / warmup_filename).read_bytes(),
                candidates,
            )
            print(
                json.dumps(
                    {
                        "path": "openclip_warmup",
                        "productId": warmup_product_id,
                        "queryFile": warmup_filename,
                        "elapsedMs": round((perf_counter() - warmup_started_at) * 1000, 2),
                    },
                    ensure_ascii=False,
                )
            )
            for product_id, query_filename in queries:
                query_path = FIXTURE_ROOT / "query" / query_filename
                query_bytes = query_path.read_bytes()
                for repeat in range(args.repeats):
                    started_at = perf_counter()
                    decision = _run(event_loop, fast_provider, query_bytes, candidates)
                    elapsed_ms = (perf_counter() - started_at) * 1000
                    print(
                        json.dumps(
                            {
                                "path": "openclip_plus_fallback",
                                "productId": product_id,
                                "repeat": repeat + 1,
                                "queryFile": query_filename,
                                "elapsedMs": round(elapsed_ms, 2),
                                "status": decision.status,
                                "matchedProductId": decision.product_id,
                                **_telemetry_dict(decision),
                            },
                            ensure_ascii=False,
                        )
                    )

                if openai_provider is not None and not args.all_query_fixtures:
                    started_at = perf_counter()
                    decision = _run(event_loop, openai_provider, query_bytes, candidates)
                    print(
                        json.dumps(
                            {
                                "path": "openai_only",
                                "productId": product_id,
                                "elapsedMs": round((perf_counter() - started_at) * 1000, 2),
                                "status": decision.status,
                                "matchedProductId": decision.product_id,
                            },
                            ensure_ascii=False,
                        )
                    )
        finally:
            if openai_provider is not None:
                _run_close(event_loop, openai_provider)
            event_loop.close()


def _run(
    event_loop: asyncio.AbstractEventLoop,
    provider: RecognitionProvider,
    image_bytes: bytes,
    candidates: list[RecognitionCandidate],
) -> RecognitionDecision:
    return event_loop.run_until_complete(provider.recognize(image_bytes, candidates))


def _run_close(event_loop: asyncio.AbstractEventLoop, provider: OpenAIRecognitionProvider) -> None:
    event_loop.run_until_complete(provider.close())


def _jpeg_data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _telemetry_dict(decision: RecognitionDecision) -> dict[str, object]:
    telemetry = decision.telemetry
    if telemetry is None:
        return {}
    return {
        "embeddingGenerationMs": _round(telemetry.embedding_generation_ms),
        "vectorSearchMs": _round(telemetry.vector_search_ms),
        "fastPathTotalMs": _round(telemetry.fast_path_total_ms),
        "top1Similarity": _round(telemetry.top1_similarity),
        "top2Similarity": _round(telemetry.top2_similarity),
        "margin": _round(telemetry.similarity_margin),
        "fastPathMatched": telemetry.fast_path_matched,
        "openaiFallback": telemetry.openai_fallback,
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


if __name__ == "__main__":
    main()
