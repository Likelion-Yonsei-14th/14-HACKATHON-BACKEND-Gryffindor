from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.domain.enums import PurchaseState, RecognitionStatus, SessionStatus, TriggerType


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SessionCreateRequest(ApiModel):
    currency: Literal["USD", "CNY"]
    store_id: UUID


class SessionResponse(ApiModel):
    session_id: UUID
    status: SessionStatus
    currency: str
    store_id: UUID
    started_at: datetime


class StoreResponse(ApiModel):
    id: UUID
    name: str
    brand: str
    country: str
    city: str
    type: str
    airport_code: str | None


class StoreListResponse(ApiModel):
    stores: list[StoreResponse]


class SessionCompleteResponse(ApiModel):
    session_id: UUID
    status: SessionStatus
    completed_at: datetime


class ProductResponse(ApiModel):
    product_id: str
    sku: str
    brand: str
    name: str
    category: str
    image_url: str


class PriceQuoteResponse(ApiModel):
    retail_price_krw: int
    estimated_refund_krw: int
    estimated_refund_price_krw: int
    converted_retail_price: Decimal | None
    converted_estimated_refund: Decimal | None
    converted_estimated_refund_price: Decimal | None
    converted_amount: Decimal | None
    converted_currency: str
    instant_refund_eligible: bool
    pricing_mode: Literal["MOCK"] = "MOCK"


class ObservationResponse(ApiModel):
    trigger_type: TriggerType
    occupancy_ratio: float
    dwell_ms: int
    first_observed_at: datetime
    last_observed_at: datetime


class ObservedProductResponse(ApiModel):
    product: ProductResponse
    pricing: PriceQuoteResponse
    observation: ObservationResponse


class RecognitionResponse(ApiModel):
    recognition_status: RecognitionStatus
    is_new: bool | None = None
    observed_product: ObservedProductResponse | None = None
    candidate_product_ids: list[str] | None = None


class ProductListItemResponse(ApiModel):
    product: ProductResponse
    pricing: PriceQuoteResponse
    purchase_state: PurchaseState
    interested: bool


class SessionProductListResponse(ApiModel):
    session_id: UUID
    items: list[ProductListItemResponse]


class ErrorDetail(ApiModel):
    code: str
    message: str


class ErrorResponse(ApiModel):
    error: ErrorDetail


class WishlistResponse(ApiModel):
    items: list[ProductResponse]


class ReceiptItemResponse(ApiModel):
    name: str
    product_id: str | None
    quantity: int | None
    price: int | None


class ReceiptResponse(ApiModel):
    id: UUID
    store_name: str
    purchased_at: datetime | None
    total_amount: int | None
    currency: str | None
    items: list[ReceiptItemResponse]
    created_at: datetime


class FlightResponse(ApiModel):
    id: UUID
    departure_airport: str
    arrival_airport: str
    flight_number: str | None
    departure_at: datetime | None
    created_at: datetime


class RecommendationProductResponse(ApiModel):
    product: ProductResponse
    reason: str


class RecommendationStoreResponse(ApiModel):
    store_id: UUID
    name: str
    reason: str
    products: list[RecommendationProductResponse]


class RecommendationResponse(ApiModel):
    stores: list[RecommendationStoreResponse]


class UserResponse(ApiModel):
    id: int
    name: str


class MyPageResponse(ApiModel):
    user: UserResponse
    wishlist: list[ProductResponse]
    receipts: list[ReceiptResponse]
    flight: FlightResponse | None
