from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.domain.enums import PurchaseState, RecognitionStatus, SessionStatus, TriggerType


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SessionCreateRequest(ApiModel):
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")


class SessionResponse(ApiModel):
    session_id: UUID
    status: SessionStatus
    currency: str
    started_at: datetime


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
    converted_amount: Decimal
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
