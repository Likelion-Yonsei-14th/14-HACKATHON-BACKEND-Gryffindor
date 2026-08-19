from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
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
    store_name: str | None
    purchased_at: datetime | None
    total_amount: int | None
    currency: str | None
    items: list[ReceiptItemResponse]
    created_at: datetime


class FlightResponse(ApiModel):
    id: UUID
    departure_airport: str | None
    arrival_airport: str | None
    terminal: str | None
    flight_number: str | None
    departure_at: datetime | None
    arrival_at: datetime | None
    airport_arrival_at: datetime | None
    created_at: datetime


class FlightPatchRequest(ApiModel):
    departure_airport: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    arrival_airport: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    terminal: str | None = Field(default=None, min_length=1, max_length=100)
    flight_number: str | None = Field(default=None, min_length=2, max_length=20)
    departure_at: datetime | None = None
    arrival_at: datetime | None = None
    airport_arrival_at: datetime | None = None

    @field_validator("departure_at", "arrival_at", "airport_arrival_at")
    @classmethod
    def require_aware_flight_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("flight timestamps must include a timezone offset")
        return value


class PurchaseItemResponse(ApiModel):
    purchase_item_id: UUID
    product: ProductResponse | None
    fallback_product_name: str | None
    quantity: int | None
    price: int | None


class PurchaseResponse(ApiModel):
    id: UUID
    store_name: str | None
    purchased_at: datetime | None
    total_amount: int | None
    currency: str | None
    items: list[PurchaseItemResponse]
    created_at: datetime


class PurchasedProductResponse(ApiModel):
    purchase_item_id: UUID
    product: ProductResponse | None
    fallback_product_name: str | None
    quantity: int | None
    price: int | None
    currency: str | None
    store_name: str | None
    purchased_at: datetime | None


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
    purchased_products: list[PurchasedProductResponse]
    flight: FlightResponse | None
