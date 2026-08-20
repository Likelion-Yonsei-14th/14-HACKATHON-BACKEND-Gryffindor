import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.errors import AppError
from app.models.personalization import Flight, Receipt, ReceiptItem
from app.models.product import Product
from app.models.shopping import SessionProduct
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
from app.services.exchange_rates import ExchangeRateService
from app.services.images import read_valid_image
from app.services.personalization import PersonalizationService
from app.services.pricing import PriceQuote, PricingService
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
def my_page(
    db: DbSession,
    currency: Annotated[str | None, Query()] = "USD",
) -> MyPageResponse:
    service = PersonalizationService(db)
    user = service.user()
    purchases = service.list_purchases()

    # Set up pricing service for currency conversion
    target_currency = (currency or "USD").upper()
    if target_currency not in ("USD", "CNY"):
        target_currency = "USD"
    pricing_service = PricingService(ExchangeRateService(db))

    # Receipt-based purchased products
    receipt_purchased = [
        _purchased_product_response_with_pricing(purchase, item, pricing_service, target_currency)
        for purchase in purchases
        for item in purchase.items
    ]

    # Collect product IDs already covered by receipts (for dedup)
    receipt_product_ids: set[str] = set()
    for purchase in purchases:
        for item in purchase.items:
            if item.product is not None:
                receipt_product_ids.add(item.product.product_id)

    # Session-based purchased products (deduplicated against receipts)
    session_purchased = service.list_session_purchased_products()
    for sp in session_purchased:
        if sp.product.product_id in receipt_product_ids:
            continue
        receipt_product_ids.add(sp.product.product_id)  # prevent duplicates within sessions
        receipt_purchased.append(
            _session_purchased_product_response_with_pricing(sp, pricing_service, target_currency)
        )

    return MyPageResponse(
        user=UserResponse(id=user.id, name=user.name),
        wishlist=[_product_response(item.product) for item in service.list_wishlist()],
        purchased_products=receipt_purchased,
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


def _purchased_product_response_with_pricing(
    purchase: Receipt,
    item: ReceiptItem,
    pricing_service: PricingService,
    target_currency: str,
) -> PurchasedProductResponse:
    price_krw = item.price or 0
    quote: PriceQuote | None = None
    if price_krw > 0:
        if item.product is not None:
            quote = pricing_service.quote(item.product, target_currency)
        else:
            quote = pricing_service.quote_price(price_krw, target_currency)

    return PurchasedProductResponse(
        purchase_item_id=item.id,
        product=_product_response(item.product) if item.product is not None else None,
        fallback_product_name=item.product_name if item.product is None else None,
        quantity=item.quantity,
        price=item.price,
        currency=purchase.currency,
        store_name=purchase.store_name,
        purchased_at=purchase.purchased_at,
        estimated_refund_krw=quote.estimated_refund_krw if quote else None,
        estimated_refund_price_krw=quote.estimated_refund_price_krw if quote else None,
        converted_price=quote.converted_retail_price if quote else None,
        converted_estimated_refund=quote.converted_estimated_refund if quote else None,
        converted_estimated_refund_price=quote.converted_estimated_refund_price if quote else None,
        converted_currency=target_currency if quote else None,
    )


def _session_purchased_product_response_with_pricing(
    session_product: SessionProduct,
    pricing_service: PricingService,
    target_currency: str,
) -> PurchasedProductResponse:
    shopping_session = session_product.shopping_session
    product = session_product.product
    purchased_at = shopping_session.completed_at or shopping_session.started_at
    quote = pricing_service.quote(product, target_currency)
    return PurchasedProductResponse(
        purchase_item_id=session_product.id,
        product=_product_response(product),
        fallback_product_name=None,
        quantity=1,
        price=product.retail_price_krw,
        currency="KRW",
        store_name=shopping_session.store.name if shopping_session.store else None,
        purchased_at=purchased_at,
        estimated_refund_krw=quote.estimated_refund_krw,
        estimated_refund_price_krw=quote.estimated_refund_price_krw,
        converted_price=quote.converted_retail_price,
        converted_estimated_refund=quote.converted_estimated_refund,
        converted_estimated_refund_price=quote.converted_estimated_refund_price,
        converted_currency=target_currency,
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
