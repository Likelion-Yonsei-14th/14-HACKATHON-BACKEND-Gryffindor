from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class RecommendationModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class ViewedProductContext(RecommendationModel):
    product_id: str
    observation_count: int
    max_dwell_ms: int
    store_ids: list[UUID]


class PurchasedProductContext(RecommendationModel):
    product_id: str | None
    name: str | None
    brand: str | None
    category: str | None
    fallback_product_name: str | None
    store_name: str | None


class FlightContext(RecommendationModel):
    departure_airport: str | None
    arrival_airport: str | None
    terminal: str | None
    departure_at: datetime | None
    arrival_at: datetime | None
    airport_arrival_at: datetime | None


class TripContext(RecommendationModel):
    trip_id: UUID
    title: str
    destination_city: str | None
    destination_country: str | None
    starts_at: datetime | None
    ends_at: datetime | None


class HotelContext(RecommendationModel):
    name: str
    address: str | None
    latitude: float | None
    longitude: float | None
    check_in_at: datetime | None
    check_out_at: datetime | None


class CandidateStoreContext(RecommendationModel):
    store_id: UUID
    name: str
    country: str
    city: str | None
    type: str
    airport_code: str | None
    product_ids: list[str]
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    terminal: str | None = None
    opening_hours: str | None = None
    distance_from_current_location_km: float | None = None
    distance_from_hotel_km: float | None = None
    airport_match: bool = False
    terminal_match: bool = False
    has_wishlist_items: bool = False


class CandidateProductContext(RecommendationModel):
    product_id: str
    sku: str
    brand: str
    name: str
    category: str
    store_ids: list[UUID]
    description: str | None = None


class RecommendationContext(RecommendationModel):
    wishlist_product_ids: list[str]
    viewed_products: list[ViewedProductContext]
    purchased_product_ids: list[str]
    purchased_products: list[PurchasedProductContext]
    latest_flight: FlightContext | None
    candidate_stores: list[CandidateStoreContext]
    candidate_products: list[CandidateProductContext]
    trip: TripContext | None = None
    hotel: HotelContext | None = None


class RecommendationProductDecision(RecommendationModel):
    product_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class RecommendationStoreDecision(RecommendationModel):
    store_id: UUID
    reason: str = Field(min_length=1, max_length=500)
    products: list[RecommendationProductDecision] = Field(max_length=10)


class RecommendationDecision(RecommendationModel):
    stores: list[RecommendationStoreDecision] = Field(max_length=10)


class RecommendationProviderError(Exception):
    """A retryable or malformed response from the recommendation provider."""


class RecommendationProvider(Protocol):
    async def recommend(self, context: RecommendationContext) -> RecommendationDecision: ...
