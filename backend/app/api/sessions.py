import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Path, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.domain.enums import RecognitionStatus, TriggerType
from app.errors import AppError
from app.models.product import Product
from app.models.shopping import SessionProduct
from app.providers.openai_recognition import OpenAIRecognitionProvider
from app.providers.openclip_embedding import OpenCLIPImageEmbedder
from app.providers.openclip_recognition import OpenCLIPRecognitionProvider
from app.providers.recognition import RecognitionProvider
from app.providers.scripted_recognition import ScriptedRecognitionProvider
from app.repositories.product_embeddings import ProductEmbeddingRepository
from app.schemas.api import (
    ErrorResponse,
    ObservationResponse,
    ObservedProductResponse,
    PriceQuoteResponse,
    ProductListItemResponse,
    ProductResponse,
    RecognitionResponse,
    SessionCompleteResponse,
    SessionCreateRequest,
    SessionProductListResponse,
    SessionResponse,
    SessionReviewRequest,
    SessionReviewResponse,
)
from app.services.images import read_valid_image, save_recognition_debug_image
from app.services.pricing import PriceQuote
from app.services.shopping import RecognitionResult, RecognitionService, ShoppingSessionService

router = APIRouter(prefix="/api/v1", tags=["shopping"])
logger = logging.getLogger(__name__)
DbSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_scripted_recognition_provider(settings: AppSettings) -> ScriptedRecognitionProvider:
    return ScriptedRecognitionProvider(
        status=RecognitionStatus(settings.scripted_recognition_status),
        product_id=settings.scripted_recognition_product_id,
    )


async def get_recognition_provider(
    settings: AppSettings,
    db: DbSession,
) -> AsyncIterator[RecognitionProvider]:
    if settings.recognition_provider == "scripted":
        yield get_scripted_recognition_provider(settings)
        return

    if settings.recognition_provider == "openclip":
        provider = OpenCLIPRecognitionProvider(
            embedder=OpenCLIPImageEmbedder(
                model_name=settings.openclip_model,
                pretrained=settings.openclip_pretrained,
                device=settings.openclip_device,
                expected_dimension=settings.openclip_embedding_dimension,
            ),
            searcher=ProductEmbeddingRepository(db),
            match_threshold=settings.openclip_match_threshold,
            margin_threshold=settings.openclip_margin_threshold,
        )
    else:
        if settings.openai_api_key is None:
            raise _recognition_provider_unavailable()
        api_key = settings.openai_api_key.get_secret_value()
        if not api_key:
            raise _recognition_provider_unavailable()
        provider = _get_openai_recognition_provider(
            api_key,
            settings.openai_vision_model,
            settings.openai_timeout_seconds,
        )
    try:
        yield provider
    finally:
        await provider.close()


def _get_openai_recognition_provider(
    api_key: str,
    model: str,
    timeout_seconds: float,
) -> OpenAIRecognitionProvider:
    return OpenAIRecognitionProvider(
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )


RecognitionProviderDependency = Annotated[
    RecognitionProvider,
    Depends(get_recognition_provider),
]


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}},
)
def create_session(payload: SessionCreateRequest, db: DbSession) -> SessionResponse:
    shopping_session = ShoppingSessionService(db).create(payload.currency, payload.store_id)
    return SessionResponse(
        session_id=shopping_session.id,
        status=shopping_session.status,
        currency=shopping_session.currency,
        store_id=shopping_session.store_id,
        started_at=shopping_session.started_at,
    )


@router.post(
    "/sessions/{sessionId}/complete",
    response_model=SessionCompleteResponse,
    responses={404: {"model": ErrorResponse}},
)
def complete_session(
    session_id: Annotated[UUID, Path(alias="sessionId")],
    db: DbSession,
) -> SessionCompleteResponse:
    shopping_session = ShoppingSessionService(db).complete(session_id)
    if shopping_session.completed_at is None:
        raise RuntimeError("Completed session is missing completed_at")
    return SessionCompleteResponse(
        session_id=shopping_session.id,
        status=shopping_session.status,
        completed_at=shopping_session.completed_at,
    )


@router.put(
    "/sessions/{sessionId}/review",
    response_model=SessionReviewResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def submit_review(
    session_id: Annotated[UUID, Path(alias="sessionId")],
    payload: SessionReviewRequest,
    db: DbSession,
) -> SessionReviewResponse:
    purchased, interested = ShoppingSessionService(db).submit_review(
        session_id,
        payload.purchased_product_ids,
        payload.interested_product_ids,
    )
    return SessionReviewResponse(
        purchased_product_ids=purchased,
        interested_product_ids=interested,
    )


@router.post(
    "/sessions/{sessionId}/recognize",
    response_model=RecognitionResponse,
    response_model_exclude_none=True,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def recognize_product(
    session_id: Annotated[UUID, Path(alias="sessionId")],
    image: Annotated[UploadFile, File()],
    captured_at: Annotated[datetime, Form(alias="capturedAt")],
    trigger_type: Annotated[TriggerType, Form(alias="triggerType")],
    occupancy_ratio: Annotated[float, Form(alias="occupancyRatio", ge=0, le=1)],
    dwell_ms: Annotated[int, Form(alias="dwellMs", ge=0)],
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    provider: RecognitionProviderDependency,
    tracking_id: Annotated[str | None, Form(alias="trackingId")] = None,
) -> RecognitionResponse:
    del tracking_id
    request_started_at = perf_counter()
    supplied_request_id = (request.headers.get("X-Request-ID") or "").strip()
    request_id = supplied_request_id if 0 < len(supplied_request_id) <= 128 else uuid4().hex
    response.headers["X-Request-ID"] = request_id
    image_bytes = await read_valid_image(image, settings.recognition_max_image_bytes)
    normalized_captured_at = _as_utc(captured_at)
    if settings.recognition_debug_save_images:
        try:
            saved_image_path = await save_recognition_debug_image(
                image_bytes,
                directory=settings.recognition_debug_image_dir,
                session_id=session_id,
                captured_at=normalized_captured_at,
            )
        except Exception:
            logger.warning(
                "recognition_debug_image_save_failed request_id=%s session_id=%s",
                request_id,
                session_id,
                exc_info=True,
            )
        else:
            logger.info(
                "recognition_debug_image_saved request_id=%s session_id=%s path=%s",
                request_id,
                session_id,
                saved_image_path,
            )
    recognition_started_at = perf_counter()
    result = await RecognitionService(
        db,
        provider,
        candidate_limit=settings.recognition_max_candidates,
    ).recognize(
        session_id=session_id,
        image_bytes=image_bytes,
        captured_at=normalized_captured_at,
        trigger_type=trigger_type,
        occupancy_ratio=occupancy_ratio,
        dwell_ms=dwell_ms,
    )
    recognition_latency_ms = (perf_counter() - recognition_started_at) * 1000
    api_response = _recognition_response(result)
    product_id = result.product.product_id if result.product is not None else None
    logger.info(
        "recognition_completed request_id=%s session_id=%s image_bytes=%d provider=%s "
        "trigger_type=%s occupancy_ratio=%.4f dwell_ms=%d recognition_status=%s "
        "product_id=%s recognition_latency_ms=%.2f total_latency_ms=%.2f",
        request_id,
        session_id,
        len(image_bytes),
        type(provider).__name__,
        trigger_type,
        occupancy_ratio,
        dwell_ms,
        result.status,
        product_id,
        recognition_latency_ms,
        (perf_counter() - request_started_at) * 1000,
    )
    if result.telemetry is not None:
        logger.info(
            "recognition_fast_path request_id=%s provider=%s embeddingGenerationMs=%s "
            "vectorSearchMs=%s fastPathTotalMs=%s top1Similarity=%s top2Similarity=%s "
            "margin=%s fastPathMatched=%s openaiFallback=%s",
            request_id,
            result.telemetry.provider,
            _metric(result.telemetry.embedding_generation_ms),
            _metric(result.telemetry.vector_search_ms),
            _metric(result.telemetry.fast_path_total_ms),
            _metric(result.telemetry.top1_similarity),
            _metric(result.telemetry.top2_similarity),
            _metric(result.telemetry.similarity_margin),
            result.telemetry.fast_path_matched,
            result.telemetry.openai_fallback,
        )
    return api_response


@router.get(
    "/sessions/{sessionId}/products",
    response_model=SessionProductListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_session_products(
    session_id: Annotated[UUID, Path(alias="sessionId")],
    db: DbSession,
) -> SessionProductListResponse:
    service = ShoppingSessionService(db)
    shopping_session, session_products = service.list_products(session_id)
    items = [
        ProductListItemResponse(
            product=_product_response(session_product.product),
            pricing=_pricing_response(
                service.price_for(session_product.product, shopping_session.currency)
            ),
            purchase_state=session_product.purchase_state,
            interested=session_product.interested,
        )
        for session_product in session_products
    ]
    return SessionProductListResponse(session_id=shopping_session.id, items=items)


def _recognition_response(result: RecognitionResult) -> RecognitionResponse:
    if result.status is RecognitionStatus.AMBIGUOUS:
        return RecognitionResponse(
            recognition_status=result.status,
            candidate_product_ids=list(result.candidate_product_ids),
        )
    if result.status is RecognitionStatus.UNKNOWN:
        return RecognitionResponse(recognition_status=result.status)

    if (
        result.product is None
        or result.session_product is None
        or result.pricing is None
        or result.is_new is None
    ):
        raise RuntimeError("MATCHED recognition result is incomplete")

    return RecognitionResponse(
        recognition_status=result.status,
        is_new=result.is_new,
        observed_product=ObservedProductResponse(
            product=_product_response(result.product),
            pricing=_pricing_response(result.pricing),
            observation=_observation_response(result.session_product),
        ),
    )


def _product_response(product: Product) -> ProductResponse:
    return ProductResponse(
        product_id=product.product_id,
        sku=product.sku,
        brand=product.brand,
        name=product.name,
        category=product.category,
        image_url=product.image_url,
    )


def _pricing_response(quote: PriceQuote) -> PriceQuoteResponse:
    return PriceQuoteResponse(
        retail_price_krw=quote.retail_price_krw,
        estimated_refund_krw=quote.estimated_refund_krw,
        estimated_refund_price_krw=quote.estimated_refund_price_krw,
        converted_retail_price=quote.converted_retail_price,
        converted_estimated_refund=quote.converted_estimated_refund,
        converted_estimated_refund_price=quote.converted_estimated_refund_price,
        converted_amount=quote.converted_amount,
        converted_currency=quote.converted_currency,
        instant_refund_eligible=quote.instant_refund_eligible,
    )


def _observation_response(session_product: SessionProduct) -> ObservationResponse:
    return ObservationResponse(
        trigger_type=session_product.last_trigger_type,
        occupancy_ratio=float(session_product.max_occupancy_ratio),
        dwell_ms=session_product.max_dwell_ms,
        first_observed_at=session_product.first_observed_at,
        last_observed_at=session_product.last_observed_at,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _metric(value: float | None) -> str:
    return "none" if value is None else f"{value:.4f}"


def _recognition_provider_unavailable() -> AppError:
    return AppError(
        503,
        "RECOGNITION_PROVIDER_ERROR",
        "The recognition provider is temporarily unavailable.",
    )
