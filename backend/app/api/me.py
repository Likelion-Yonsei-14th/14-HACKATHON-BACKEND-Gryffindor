import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.errors import AppError
from app.models.personalization import Flight, Receipt, ReceiptItem
from app.models.product import Product
from app.providers.documents import DocumentExtractionProvider
from app.providers.openai_documents import OpenAIDocumentExtractionProvider
from app.providers.openai_recommendation import OpenAIRecommendationProvider
from app.providers.recommendation import RecommendationProvider
from app.schemas.api import (
    ErrorResponse,
    FlightPatchRequest,
    FlightResponse,
    MyPageResponse,
    ProductResponse,
    PurchasedProductResponse,
    PurchaseItemResponse,
    PurchaseRefundMethodPatchRequest,
    PurchaseResponse,
    ReceiptItemResponse,
    ReceiptResponse,
    RecommendationProductResponse,
    RecommendationResponse,
    RecommendationStoreResponse,
    TripSummaryResponse,
    UserResponse,
    WishlistResponse,
)
from app.services.images import read_valid_image
from app.services.personalization import PersonalizationService
from app.services.recommendations import RecommendationService
from app.services.trips import TripService

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
    trip_id: Annotated[UUID | None, Form(alias="tripId")] = None,
) -> ReceiptResponse:
    image_bytes = await read_valid_image(image, settings.recognition_max_image_bytes)
    receipt = await PersonalizationService(db).analyze_receipt(image_bytes, provider, trip_id)
    logger.info(
        "receipt_extraction_completed receipt_id=%s provider=%s image_bytes=%d items=%d",
        receipt.id,
        type(provider).__name__,
        len(image_bytes),
        len(receipt.items),
    )
    return _receipt_response(receipt)


@router.get("/purchases", response_model=list[PurchaseResponse])
def list_purchases(db: DbSession) -> list[PurchaseResponse]:
    purchases = PersonalizationService(db).list_purchases()
    return [_purchase_response(purchase) for purchase in purchases]


@router.patch(
    "/purchases/{purchaseId}",
    response_model=PurchaseResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_purchase_refund_method(
    purchase_id: Annotated[UUID, Path(alias="purchaseId")],
    payload: PurchaseRefundMethodPatchRequest,
    db: DbSession,
) -> PurchaseResponse:
    purchase = PersonalizationService(db).update_purchase_refund_method(
        purchase_id,
        payload.refund_method,
    )
    return _purchase_response(purchase)


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
    trip_id: Annotated[UUID | None, Form(alias="tripId")] = None,
) -> FlightResponse:
    image_bytes = await read_valid_image(image, settings.recognition_max_image_bytes)
    flight = await PersonalizationService(db).analyze_flight(image_bytes, provider, trip_id)
    logger.info(
        "flight_extraction_completed flight_id=%s provider=%s image_bytes=%d",
        flight.id,
        type(provider).__name__,
        len(image_bytes),
    )
    return _flight_response(flight)


@router.patch(
    "/flights/{flightId}",
    response_model=FlightResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_flight(
    flight_id: Annotated[UUID, Path(alias="flightId")],
    payload: FlightPatchRequest,
    db: DbSession,
) -> FlightResponse:
    flight = PersonalizationService(db).update_flight(
        flight_id,
        payload.model_dump(exclude_unset=True),
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
        len(context.purchased_products),
        context.latest_flight is not None,
        len(context.candidate_products),
    )
    return RecommendationResponse(
        stores=[
            RecommendationStoreResponse(
                store_id=recommended_store.store.id,
                name=recommended_store.store.name,
                image_url=recommended_store.store.image_url,
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
    purchases = service.list_purchases()
    return MyPageResponse(
        user=UserResponse(id=user.id, name=user.name),
        wishlist=[_product_response(item.product) for item in service.list_wishlist()],
        purchased_products=[
            _purchased_product_response(purchase, item)
            for purchase in purchases
            for item in purchase.items
        ],
        flight=_optional_flight_response(service.latest_flight()),
        trips=[
            TripSummaryResponse(
                id=trip.id,
                title=trip.title,
                starts_at=trip.starts_at,
                ends_at=trip.ends_at,
            )
            for trip in TripService(db).list_trips()
        ],
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
        trip_id=receipt.trip_id,
        refund_method=receipt.refund_method,
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


def _purchase_response(purchase: Receipt) -> PurchaseResponse:
    return PurchaseResponse(
        id=purchase.id,
        trip_id=purchase.trip_id,
        refund_method=purchase.refund_method,
        store_name=purchase.store_name,
        purchased_at=purchase.purchased_at,
        total_amount=purchase.total_amount,
        currency=purchase.currency,
        items=[
            PurchaseItemResponse(
                purchase_item_id=item.id,
                product=_product_response(item.product) if item.product is not None else None,
                fallback_product_name=(item.product_name if item.product is None else None),
                quantity=item.quantity,
                price=item.price,
            )
            for item in purchase.items
        ],
        created_at=purchase.created_at,
    )


def _purchased_product_response(
    purchase: Receipt,
    item: ReceiptItem,
) -> PurchasedProductResponse:
    return PurchasedProductResponse(
        purchase_item_id=item.id,
        product=_product_response(item.product) if item.product is not None else None,
        fallback_product_name=item.product_name if item.product is None else None,
        quantity=item.quantity,
        price=item.price,
        currency=purchase.currency,
        store_name=purchase.store_name,
        purchased_at=purchase.purchased_at,
    )


def _flight_response(flight: Flight) -> FlightResponse:
    return FlightResponse(
        id=flight.id,
        trip_id=flight.trip_id,
        departure_airport=flight.departure_airport,
        arrival_airport=flight.arrival_airport,
        terminal=flight.terminal,
        flight_number=flight.flight_number,
        departure_at=flight.departure_at,
        arrival_at=flight.arrival_at,
        airport_arrival_at=flight.airport_arrival_at,
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
