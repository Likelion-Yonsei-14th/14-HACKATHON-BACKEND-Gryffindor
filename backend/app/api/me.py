import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.errors import AppError
from app.models.personalization import Flight, Receipt
from app.models.product import Product
from app.providers.documents import DocumentExtractionProvider
from app.providers.openai_documents import OpenAIDocumentExtractionProvider
from app.providers.openai_recommendation import OpenAIRecommendationProvider
from app.providers.recommendation import RecommendationProvider
from app.schemas.api import (
    ErrorResponse,
    FlightResponse,
    MyPageResponse,
    ProductResponse,
    ReceiptItemResponse,
    ReceiptResponse,
    RecommendationProductResponse,
    RecommendationResponse,
    RecommendationStoreResponse,
    UserResponse,
    WishlistResponse,
)
from app.services.images import read_valid_image
from app.services.personalization import PersonalizationService
from app.services.recommendations import RecommendationService

router = APIRouter(prefix="/api/v1/me", tags=["personalization"])
logger = logging.getLogger(__name__)
DbSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def get_document_extraction_provider(
    settings: AppSettings,
) -> AsyncIterator[DocumentExtractionProvider]:
    api_key = _openai_api_key(settings, "DOCUMENT_EXTRACTION_PROVIDER_ERROR")
    provider = OpenAIDocumentExtractionProvider(
        api_key=api_key,
        model=settings.openai_document_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    try:
        yield provider
    finally:
        await provider.close()


async def get_recommendation_provider(
    settings: AppSettings,
) -> AsyncIterator[RecommendationProvider]:
    api_key = _openai_api_key(settings, "RECOMMENDATION_PROVIDER_ERROR")
    provider = OpenAIRecommendationProvider(
        api_key=api_key,
        model=settings.openai_recommendation_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    try:
        yield provider
    finally:
        await provider.close()


DocumentProviderDependency = Annotated[
    DocumentExtractionProvider,
    Depends(get_document_extraction_provider),
]
RecommendationProviderDependency = Annotated[
    RecommendationProvider,
    Depends(get_recommendation_provider),
]


@router.get("/wishlist", response_model=WishlistResponse)
def list_wishlist(db: DbSession) -> WishlistResponse:
    wishlist = PersonalizationService(db).list_wishlist()
    return WishlistResponse(items=[_product_response(item.product) for item in wishlist])


@router.post(
    "/wishlist/{productId}",
    response_model=ProductResponse,
    responses={404: {"model": ErrorResponse}},
)
def add_wishlist(
    product_id: Annotated[str, Path(alias="productId", min_length=1, max_length=64)],
    db: DbSession,
) -> ProductResponse:
    product = PersonalizationService(db).add_wishlist(product_id)
    return _product_response(product)


@router.delete("/wishlist/{productId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wishlist(
    product_id: Annotated[str, Path(alias="productId", min_length=1, max_length=64)],
    db: DbSession,
) -> Response:
    PersonalizationService(db).delete_wishlist(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/receipts/analyze",
    response_model=ReceiptResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def analyze_receipt(
    image: Annotated[UploadFile, File()],
    db: DbSession,
    settings: AppSettings,
    provider: DocumentProviderDependency,
) -> ReceiptResponse:
    image_bytes = await read_valid_image(image, settings.recognition_max_image_bytes)
    receipt = await PersonalizationService(db).analyze_receipt(image_bytes, provider)
    logger.info(
        "receipt_extraction_completed receipt_id=%s provider=%s image_bytes=%d items=%d",
        receipt.id,
        type(provider).__name__,
        len(image_bytes),
        len(receipt.items),
    )
    return _receipt_response(receipt)


@router.post(
    "/flights/analyze",
    response_model=FlightResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def analyze_flight(
    image: Annotated[UploadFile, File()],
    db: DbSession,
    settings: AppSettings,
    provider: DocumentProviderDependency,
) -> FlightResponse:
    image_bytes = await read_valid_image(image, settings.recognition_max_image_bytes)
    flight = await PersonalizationService(db).analyze_flight(image_bytes, provider)
    logger.info(
        "flight_extraction_completed flight_id=%s provider=%s image_bytes=%d",
        flight.id,
        type(provider).__name__,
        len(image_bytes),
    )
    return _flight_response(flight)


@router.get(
    "/recommendations",
    response_model=RecommendationResponse,
    responses={503: {"model": ErrorResponse}},
)
async def recommendations(
    db: DbSession,
    settings: AppSettings,
    provider: RecommendationProviderDependency,
) -> RecommendationResponse:
    result, context = await RecommendationService(
        db,
        provider,
        candidate_limit=settings.recommendation_max_candidates,
    ).recommend()
    logger.info(
        "recommendation_completed provider=%s stores=%d wishlist=%d viewed=%d purchased=%d "
        "flight_present=%s candidates=%d",
        type(provider).__name__,
        len(result.stores),
        len(context.wishlist_product_ids),
        len(context.viewed_products),
        len(context.purchased_product_ids),
        context.latest_flight is not None,
        len(context.candidate_products),
    )
    return RecommendationResponse(
        stores=[
            RecommendationStoreResponse(
                store_id=recommended_store.store.id,
                name=recommended_store.store.name,
                reason=recommended_store.reason,
                products=[
                    RecommendationProductResponse(
                        product=_product_response(recommended_product.product),
                        reason=recommended_product.reason,
                    )
                    for recommended_product in recommended_store.products
                ],
            )
            for recommended_store in result.stores
        ]
    )


@router.get("", response_model=MyPageResponse)
def my_page(db: DbSession) -> MyPageResponse:
    service = PersonalizationService(db)
    user = service.user()
    return MyPageResponse(
        user=UserResponse(id=user.id, name=user.name),
        wishlist=[_product_response(item.product) for item in service.list_wishlist()],
        receipts=[_receipt_response(receipt) for receipt in service.list_receipts()],
        flight=_optional_flight_response(service.latest_flight()),
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


def _receipt_response(receipt: Receipt) -> ReceiptResponse:
    return ReceiptResponse(
        id=receipt.id,
        store_name=receipt.store_name,
        purchased_at=receipt.purchased_at,
        total_amount=receipt.total_amount,
        currency=receipt.currency,
        items=[
            ReceiptItemResponse(
                name=item.product_name,
                product_id=item.product.product_id if item.product is not None else None,
                quantity=item.quantity,
                price=item.price,
            )
            for item in receipt.items
        ],
        created_at=receipt.created_at,
    )


def _flight_response(flight: Flight) -> FlightResponse:
    return FlightResponse(
        id=flight.id,
        departure_airport=flight.departure_airport,
        arrival_airport=flight.arrival_airport,
        flight_number=flight.flight_number,
        departure_at=flight.departure_at,
        created_at=flight.created_at,
    )


def _optional_flight_response(flight: Flight | None) -> FlightResponse | None:
    return _flight_response(flight) if flight is not None else None


def _openai_api_key(settings: Settings, error_code: str) -> str:
    if settings.openai_api_key is not None:
        api_key = settings.openai_api_key.get_secret_value()
        if api_key:
            return api_key
    raise AppError(503, error_code, "The OpenAI provider is temporarily unavailable.")
