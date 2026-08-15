from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.domain.enums import RecognitionStatus, TriggerType
from app.models.product import Product
from app.models.shopping import SessionProduct
from app.providers.mock_recognition import MockRecognitionProvider
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
)
from app.services.images import read_valid_image
from app.services.pricing import PriceQuote
from app.services.shopping import RecognitionResult, RecognitionService, ShoppingSessionService

router = APIRouter(prefix="/api/v1", tags=["shopping"])
DbSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_mock_recognition_provider(settings: AppSettings) -> MockRecognitionProvider:
    return MockRecognitionProvider(
        status=RecognitionStatus(settings.mock_recognition_status),
        product_id=settings.mock_recognition_product_id,
    )


RecognitionProviderDependency = Annotated[
    MockRecognitionProvider,
    Depends(get_mock_recognition_provider),
]


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(payload: SessionCreateRequest, db: DbSession) -> SessionResponse:
    shopping_session = ShoppingSessionService(db).create(payload.currency)
    return SessionResponse(
        session_id=shopping_session.id,
        status=shopping_session.status,
        currency=shopping_session.currency,
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


@router.post(
    "/sessions/{sessionId}/recognize",
    response_model=RecognitionResponse,
    response_model_exclude_none=True,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
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
    db: DbSession,
    settings: AppSettings,
    provider: RecognitionProviderDependency,
    tracking_id: Annotated[str | None, Form(alias="trackingId")] = None,
) -> RecognitionResponse:
    del tracking_id
    image_bytes = await read_valid_image(image, settings.recognition_max_image_bytes)
    normalized_captured_at = _as_utc(captured_at)
    result = await RecognitionService(db, provider).recognize(
        session_id=session_id,
        image_bytes=image_bytes,
        captured_at=normalized_captured_at,
        trigger_type=trigger_type,
        occupancy_ratio=occupancy_ratio,
        dwell_ms=dwell_ms,
    )
    return _recognition_response(result)


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
