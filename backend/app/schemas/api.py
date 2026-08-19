from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.domain.enums import (
    PurchaseState,
    RecognitionStatus,
    RefundChecklistStatus,
    RefundMethod,
    ReservationStatus,
    SessionStatus,
    TriggerType,
)


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
    city: str | None
    type: str
    airport_code: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    terminal: str | None
    opening_hours: str | None


class StoreListResponse(ApiModel):
    stores: list[StoreResponse]


class NearbyStoreResponse(ApiModel):
    store_id: UUID
    name: str
    type: str
    address: str | None
    latitude: float
    longitude: float
    distance_km: float
    airport_code: str | None
    terminal: str | None


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
    trip_id: UUID | None
    refund_method: RefundMethod
    store_name: str | None
    purchased_at: datetime | None
    total_amount: int | None
    currency: str | None
    items: list[ReceiptItemResponse]
    created_at: datetime


class FlightResponse(ApiModel):
    id: UUID
    trip_id: UUID | None
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
    trip_id: UUID | None
    refund_method: RefundMethod
    store_name: str | None
    purchased_at: datetime | None
    total_amount: int | None
    currency: str | None
    items: list[PurchaseItemResponse]
    created_at: datetime


class PurchaseRefundMethodPatchRequest(ApiModel):
    refund_method: RefundMethod


class RefundChecklistItemResponse(ApiModel):
    id: str
    title: str
    description: str
    required: bool


class RefundChecklistResponse(ApiModel):
    trip_id: UUID
    status: RefundChecklistStatus
    items: list[RefundChecklistItemResponse]
    notice: str | None


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


class TripCreateRequest(ApiModel):
    title: str = Field(min_length=1, max_length=120)
    destination_city: str | None = Field(default=None, max_length=120)
    destination_country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_aware_trip_time(cls, value: datetime | None) -> datetime | None:
        return _require_aware_datetime(value, "trip timestamps")

    @model_validator(mode="after")
    def validate_time_order(self) -> "TripCreateRequest":
        _validate_time_order(self.starts_at, self.ends_at)
        return self


class TripPatchRequest(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    destination_city: str | None = Field(default=None, max_length=120)
    destination_country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_aware_trip_time(cls, value: datetime | None) -> datetime | None:
        return _require_aware_datetime(value, "trip timestamps")

    @model_validator(mode="after")
    def validate_patch(self) -> "TripPatchRequest":
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        if "starts_at" in self.model_fields_set and "ends_at" in self.model_fields_set:
            _validate_time_order(self.starts_at, self.ends_at)
        return self


class TripResponse(ApiModel):
    id: UUID
    title: str
    destination_city: str | None
    destination_country: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TripSummaryResponse(ApiModel):
    id: UUID
    title: str
    starts_at: datetime | None
    ends_at: datetime | None


class TripListResponse(ApiModel):
    trips: list[TripResponse]


class HotelStayRequest(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=1000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None

    @field_validator("check_in_at", "check_out_at")
    @classmethod
    def require_aware_hotel_time(cls, value: datetime | None) -> datetime | None:
        return _require_aware_datetime(value, "hotel timestamps")

    @model_validator(mode="after")
    def validate_time_order(self) -> "HotelStayRequest":
        _validate_time_order(self.check_in_at, self.check_out_at)
        return self


class HotelStayResponse(ApiModel):
    id: UUID
    trip_id: UUID
    name: str
    address: str | None
    latitude: float | None
    longitude: float | None
    check_in_at: datetime | None
    check_out_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VisitReservationCreateRequest(ApiModel):
    store_id: UUID
    scheduled_at: datetime
    product_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("scheduled_at")
    @classmethod
    def require_aware_scheduled_time(cls, value: datetime) -> datetime:
        aware = _require_aware_datetime(value, "scheduledAt")
        if aware is None:
            raise ValueError("scheduledAt is required")
        return aware


class ReservationStoreResponse(ApiModel):
    store_id: UUID
    name: str


class VisitReservationResponse(ApiModel):
    id: UUID
    trip_id: UUID
    store: ReservationStoreResponse
    scheduled_at: datetime
    products: list[ProductResponse]
    status: ReservationStatus
    created_at: datetime


class TripDetailResponse(ApiModel):
    trip: TripResponse
    flights: list[FlightResponse]
    hotel: HotelStayResponse | None
    visit_reservations: list[VisitReservationResponse]


class StoreWishlistProductResponse(ApiModel):
    product_id: str
    name: str


class FeedTripResponse(ApiModel):
    id: UUID
    title: str


class FeedStoreResponse(ApiModel):
    store_id: UUID
    name: str
    type: str
    distance_from_current_location_km: float | None = None
    distance_from_hotel_km: float | None
    airport_code: str | None
    terminal: str | None
    has_wishlist_items: bool
    reason: str


class FeedRecommendationResponse(ApiModel):
    product: ProductResponse
    reason: str
    stores: list[FeedStoreResponse]


class TripFeedResponse(ApiModel):
    trip: FeedTripResponse
    recommendations: list[FeedRecommendationResponse]


class UserResponse(ApiModel):
    id: int
    name: str


class MyPageResponse(ApiModel):
    user: UserResponse
    wishlist: list[ProductResponse]
    purchased_products: list[PurchasedProductResponse]
    flight: FlightResponse | None
    trips: list[TripSummaryResponse]


def _require_aware_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must include a timezone offset")
    return value


def _validate_time_order(starts_at: datetime | None, ends_at: datetime | None) -> None:
    if starts_at is not None and ends_at is not None and ends_at < starts_at:
        raise ValueError("end time must not be earlier than start time")
