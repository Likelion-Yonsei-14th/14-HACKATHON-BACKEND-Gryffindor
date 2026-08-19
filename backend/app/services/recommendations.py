import logging
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt
from uuid import UUID

from sqlalchemy.orm import Session

from app.constants import DEMO_USER_ID
from app.errors import AppError
from app.models.personalization import Flight
from app.models.product import Product
from app.models.store import Store
from app.providers.recommendation import (
    CandidateProductContext,
    CandidateStoreContext,
    FlightContext,
    HotelContext,
    PurchasedProductContext,
    RecommendationContext,
    RecommendationProvider,
    RecommendationProviderError,
    TripContext,
    ViewedProductContext,
)
from app.repositories.personalization import PersonalizationRepository
from app.repositories.trips import TripRepository

logger = logging.getLogger(__name__)

_TRIP_PRODUCT_CATEGORIES = frozenset({"bag", "perfume"})
_TRIP_STORE_TYPES = frozenset({"DEPARTMENT_STORE", "DUTY_FREE"})
_HOTEL_NEAR_DISTANCE_KM = 20.0
_TRIP_STORE_LIMIT = 10


@dataclass(frozen=True, slots=True)
class RecommendedProduct:
    product: Product
    reason: str


@dataclass(frozen=True, slots=True)
class RecommendedStore:
    store: Store
    reason: str
    products: tuple[RecommendedProduct, ...]
    distance_from_hotel_km: float | None = None
    has_wishlist_items: bool = False


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    stores: tuple[RecommendedStore, ...]


@dataclass(slots=True)
class _ViewedAggregate:
    observation_count: int = 0
    max_dwell_ms: int = 0
    store_ids: set[UUID] = field(default_factory=lambda: set[UUID]())


@dataclass(frozen=True, slots=True)
class _History:
    wishlist_ids: list[str]
    purchased_ids: list[str]
    purchased_products: list[PurchasedProductContext]
    viewed_aggregates: dict[str, _ViewedAggregate]
    viewed_products: list[ViewedProductContext]


@dataclass(frozen=True, slots=True)
class _TripStoreCandidate:
    store: Store
    eligible_products: tuple[Product, ...]
    distance_from_hotel_km: float | None
    near_hotel: bool
    airport_match: bool
    terminal_match: bool
    has_wishlist_items: bool


@dataclass(frozen=True, slots=True)
class BuiltRecommendationContext:
    context: RecommendationContext
    stores_by_id: dict[UUID, Store]
    products_by_public_id: dict[str, Product]
    product_ids_by_store: dict[UUID, frozenset[str]]
    distance_by_store: dict[UUID, float | None] = field(
        default_factory=lambda: dict[UUID, float | None]()
    )
    wishlist_match_by_store: dict[UUID, bool] = field(
        default_factory=lambda: dict[UUID, bool]()
    )


class RecommendationContextBuilder:
    def __init__(self, db: Session, *, candidate_limit: int = 50) -> None:
        self._repository = PersonalizationRepository(db)
        self._trips = TripRepository(db)
        self._candidate_limit = candidate_limit

    def build(self) -> BuiltRecommendationContext:
        history = self._build_history()
        latest_flight = self._repository.latest_flight(DEMO_USER_ID)
        stores = self._repository.list_candidate_stores()
        purchased_id_set = set(history.purchased_ids)

        candidates_by_id: dict[str, Product] = {}
        store_ids_by_product: dict[str, set[UUID]] = {}
        for store in stores:
            for store_product in store.store_products:
                product = store_product.product
                if product.product_id in purchased_id_set:
                    continue
                candidates_by_id[product.product_id] = product
                store_ids_by_product.setdefault(product.product_id, set()).add(store.id)

        prioritized_product_ids = _prioritize_product_ids(
            candidates_by_id,
            set(history.wishlist_ids),
            set(history.viewed_aggregates),
            self._candidate_limit,
        )
        selected_product_ids = set(prioritized_product_ids)
        products_by_public_id = {
            product_id: candidates_by_id[product_id] for product_id in prioritized_product_ids
        }

        airport_codes = _all_flight_airports(latest_flight)
        ordered_stores = sorted(
            stores,
            key=lambda store: (
                0 if store.airport_code in airport_codes else 1,
                str(store.id),
            ),
        )
        candidate_stores: list[CandidateStoreContext] = []
        stores_by_id: dict[UUID, Store] = {}
        product_ids_by_store: dict[UUID, frozenset[str]] = {}
        for store in ordered_stores:
            product_ids = sorted(
                store_product.product.product_id
                for store_product in store.store_products
                if store_product.product.product_id in selected_product_ids
            )
            if not product_ids:
                continue
            candidate_stores.append(_candidate_store_context(store, product_ids))
            stores_by_id[store.id] = store
            product_ids_by_store[store.id] = frozenset(product_ids)

        candidate_products = _candidate_product_contexts(
            products_by_public_id,
            store_ids_by_product,
            stores_by_id,
        )
        return BuiltRecommendationContext(
            context=RecommendationContext(
                wishlist_product_ids=history.wishlist_ids,
                viewed_products=history.viewed_products,
                purchased_product_ids=history.purchased_ids,
                purchased_products=history.purchased_products,
                latest_flight=_flight_context(latest_flight),
                candidate_stores=candidate_stores,
                candidate_products=candidate_products,
            ),
            stores_by_id=stores_by_id,
            products_by_public_id=products_by_public_id,
            product_ids_by_store=product_ids_by_store,
        )

    def build_for_trip(self, trip_id: UUID) -> BuiltRecommendationContext:
        history = self._build_history()
        trip = self._trips.get_detail(DEMO_USER_ID, trip_id)
        if trip is None:
            raise AppError(404, "TRIP_NOT_FOUND", "Trip was not found.")
        latest_flight = self._repository.latest_trip_flight(DEMO_USER_ID, trip.id)
        hotel = trip.hotel
        purchased_id_set = set(history.purchased_ids)
        wishlist_id_set = set(history.wishlist_ids)

        store_candidates: list[_TripStoreCandidate] = []
        for store in self._repository.list_candidate_stores():
            if store.type not in _TRIP_STORE_TYPES:
                continue
            eligible_products = tuple(
                store_product.product
                for store_product in store.store_products
                if store_product.product.category.casefold() in _TRIP_PRODUCT_CATEGORIES
                and store_product.product.product_id not in purchased_id_set
            )
            if not eligible_products:
                continue
            distance = (
                haversine_distance_km(
                    hotel.latitude,
                    hotel.longitude,
                    store.latitude,
                    store.longitude,
                )
                if hotel is not None
                else None
            )
            airport_match = bool(
                latest_flight is not None
                and latest_flight.departure_airport is not None
                and store.airport_code is not None
                and latest_flight.departure_airport.upper() == store.airport_code.upper()
            )
            terminal_match = bool(
                airport_match
                and latest_flight is not None
                and latest_flight.terminal
                and store.terminal
                and _normalize_terminal(latest_flight.terminal)
                == _normalize_terminal(store.terminal)
            )
            store_candidates.append(
                _TripStoreCandidate(
                    store=store,
                    eligible_products=eligible_products,
                    distance_from_hotel_km=distance,
                    near_hotel=distance is not None and distance <= _HOTEL_NEAR_DISTANCE_KM,
                    airport_match=airport_match,
                    terminal_match=terminal_match,
                    has_wishlist_items=any(
                        product.product_id in wishlist_id_set for product in eligible_products
                    ),
                )
            )

        selected_stores = sorted(store_candidates, key=_trip_store_sort_key)[:_TRIP_STORE_LIMIT]
        candidates_by_id: dict[str, Product] = {}
        store_ids_by_product: dict[str, set[UUID]] = {}
        for candidate in selected_stores:
            for product in candidate.eligible_products:
                candidates_by_id[product.product_id] = product
                store_ids_by_product.setdefault(product.product_id, set()).add(candidate.store.id)

        prioritized_product_ids = _prioritize_product_ids(
            candidates_by_id,
            wishlist_id_set,
            set(history.viewed_aggregates),
            min(self._candidate_limit, 20),
        )
        selected_product_ids = set(prioritized_product_ids)
        products_by_public_id = {
            product_id: candidates_by_id[product_id] for product_id in prioritized_product_ids
        }

        candidate_stores: list[CandidateStoreContext] = []
        stores_by_id: dict[UUID, Store] = {}
        product_ids_by_store: dict[UUID, frozenset[str]] = {}
        distance_by_store: dict[UUID, float | None] = {}
        wishlist_match_by_store: dict[UUID, bool] = {}
        for candidate in selected_stores:
            product_ids = sorted(
                product.product_id
                for product in candidate.eligible_products
                if product.product_id in selected_product_ids
            )
            if not product_ids:
                continue
            store = candidate.store
            candidate_stores.append(
                _candidate_store_context(
                    store,
                    product_ids,
                    distance_from_hotel_km=candidate.distance_from_hotel_km,
                    airport_match=candidate.airport_match,
                    terminal_match=candidate.terminal_match,
                    has_wishlist_items=candidate.has_wishlist_items,
                )
            )
            stores_by_id[store.id] = store
            product_ids_by_store[store.id] = frozenset(product_ids)
            distance_by_store[store.id] = candidate.distance_from_hotel_km
            wishlist_match_by_store[store.id] = candidate.has_wishlist_items

        return BuiltRecommendationContext(
            context=RecommendationContext(
                wishlist_product_ids=history.wishlist_ids,
                viewed_products=history.viewed_products,
                purchased_product_ids=history.purchased_ids,
                purchased_products=history.purchased_products,
                latest_flight=_flight_context(latest_flight),
                candidate_stores=candidate_stores,
                candidate_products=_candidate_product_contexts(
                    products_by_public_id,
                    store_ids_by_product,
                    stores_by_id,
                ),
                trip=TripContext(
                    trip_id=trip.id,
                    title=trip.title,
                    destination_city=trip.destination_city,
                    destination_country=trip.destination_country,
                    starts_at=trip.starts_at,
                    ends_at=trip.ends_at,
                ),
                hotel=(
                    HotelContext(
                        name=hotel.name,
                        address=hotel.address,
                        latitude=hotel.latitude,
                        longitude=hotel.longitude,
                        check_in_at=hotel.check_in_at,
                        check_out_at=hotel.check_out_at,
                    )
                    if hotel is not None
                    else None
                ),
            ),
            stores_by_id=stores_by_id,
            products_by_public_id=products_by_public_id,
            product_ids_by_store=product_ids_by_store,
            distance_by_store=distance_by_store,
            wishlist_match_by_store=wishlist_match_by_store,
        )

    def _build_history(self) -> _History:
        if self._repository.get_user(DEMO_USER_ID) is None:
            raise AppError(500, "DEMO_USER_NOT_CONFIGURED", "The demo user is not configured.")
        wishlist_items = self._repository.list_wishlist(DEMO_USER_ID)
        receipts = self._repository.list_receipts(DEMO_USER_ID)
        purchased_ids = sorted(
            {
                item.product.product_id
                for receipt in receipts
                for item in receipt.items
                if item.product is not None
            }
        )
        purchased_products = [
            PurchasedProductContext(
                product_id=item.product.product_id if item.product is not None else None,
                name=item.product.name if item.product is not None else None,
                brand=item.product.brand if item.product is not None else None,
                category=item.product.category if item.product is not None else None,
                fallback_product_name=item.product_name if item.product is None else None,
                store_name=receipt.store_name,
            )
            for receipt in receipts
            for item in receipt.items
        ]
        viewed_aggregates: dict[str, _ViewedAggregate] = {}
        for session_product in self._repository.list_recent_session_products(DEMO_USER_ID):
            public_product_id = session_product.product.product_id
            aggregate = viewed_aggregates.setdefault(public_product_id, _ViewedAggregate())
            aggregate.observation_count += session_product.observation_count
            aggregate.max_dwell_ms = max(aggregate.max_dwell_ms, session_product.max_dwell_ms)
            aggregate.store_ids.add(session_product.shopping_session.store_id)
        viewed_products = [
            ViewedProductContext(
                product_id=product_id,
                observation_count=aggregate.observation_count,
                max_dwell_ms=aggregate.max_dwell_ms,
                store_ids=sorted(aggregate.store_ids),
            )
            for product_id, aggregate in sorted(viewed_aggregates.items())
        ]
        return _History(
            wishlist_ids=[item.product.product_id for item in wishlist_items],
            purchased_ids=purchased_ids,
            purchased_products=purchased_products,
            viewed_aggregates=viewed_aggregates,
            viewed_products=viewed_products,
        )


class RecommendationService:
    def __init__(
        self,
        db: Session,
        provider: RecommendationProvider,
        *,
        candidate_limit: int,
    ) -> None:
        self._provider = provider
        self._builder = RecommendationContextBuilder(db, candidate_limit=candidate_limit)

    async def recommend(self) -> tuple[RecommendationResult, RecommendationContext]:
        return await self._recommend_built(self._builder.build())

    async def recommend_for_trip(
        self,
        trip_id: UUID,
    ) -> tuple[RecommendationResult, RecommendationContext]:
        return await self._recommend_built(self._builder.build_for_trip(trip_id))

    async def _recommend_built(
        self,
        built: BuiltRecommendationContext,
    ) -> tuple[RecommendationResult, RecommendationContext]:
        if not built.context.candidate_stores or not built.context.candidate_products:
            return RecommendationResult(stores=()), built.context

        try:
            decision = await self._provider.recommend(built.context)
        except RecommendationProviderError as exc:
            raise AppError(
                503,
                "RECOMMENDATION_PROVIDER_ERROR",
                "The recommendation provider is temporarily unavailable.",
            ) from exc

        invalid_items = 0
        seen_store_ids: set[UUID] = set()
        recommended_stores: list[RecommendedStore] = []
        for store_decision in decision.stores:
            store = built.stores_by_id.get(store_decision.store_id)
            if store is None or store.id in seen_store_ids:
                invalid_items += 1
                continue

            allowed_product_ids = built.product_ids_by_store[store.id]
            seen_product_ids: set[str] = set()
            recommended_products: list[RecommendedProduct] = []
            for product_decision in store_decision.products:
                product = built.products_by_public_id.get(product_decision.product_id)
                if (
                    product is None
                    or product.product_id not in allowed_product_ids
                    or product.product_id in seen_product_ids
                ):
                    invalid_items += 1
                    continue
                seen_product_ids.add(product.product_id)
                recommended_products.append(
                    RecommendedProduct(product=product, reason=product_decision.reason)
                )

            if not recommended_products:
                invalid_items += 1
                continue
            seen_store_ids.add(store.id)
            recommended_stores.append(
                RecommendedStore(
                    store=store,
                    reason=store_decision.reason,
                    products=tuple(recommended_products),
                    distance_from_hotel_km=built.distance_by_store.get(store.id),
                    has_wishlist_items=built.wishlist_match_by_store.get(store.id, False),
                )
            )

        if invalid_items:
            logger.warning("recommendation_validation_failed invalid_items=%d", invalid_items)
        return RecommendationResult(stores=tuple(recommended_stores)), built.context


def haversine_distance_km(
    latitude_a: float | None,
    longitude_a: float | None,
    latitude_b: float | None,
    longitude_b: float | None,
) -> float | None:
    if None in {latitude_a, longitude_a, latitude_b, longitude_b}:
        return None
    assert latitude_a is not None
    assert longitude_a is not None
    assert latitude_b is not None
    assert longitude_b is not None
    latitude_delta = radians(latitude_b - latitude_a)
    longitude_delta = radians(longitude_b - longitude_a)
    start_latitude = radians(latitude_a)
    end_latitude = radians(latitude_b)
    haversine = sin(latitude_delta / 2) ** 2 + (
        cos(start_latitude) * cos(end_latitude) * sin(longitude_delta / 2) ** 2
    )
    return round(2 * 6371.0088 * asin(sqrt(haversine)), 2)


def _prioritize_product_ids(
    candidates_by_id: dict[str, Product],
    wishlist_ids: set[str],
    viewed_ids: set[str],
    limit: int,
) -> list[str]:
    return sorted(
        candidates_by_id,
        key=lambda product_id: (
            0 if product_id in wishlist_ids else 1 if product_id in viewed_ids else 2,
            product_id,
        ),
    )[:limit]


def _candidate_product_contexts(
    products_by_public_id: dict[str, Product],
    store_ids_by_product: dict[str, set[UUID]],
    stores_by_id: dict[UUID, Store],
) -> list[CandidateProductContext]:
    return [
        CandidateProductContext(
            product_id=product.product_id,
            sku=product.sku,
            brand=product.brand,
            name=product.name,
            category=product.category,
            description=_product_description(product),
            store_ids=sorted(
                store_id
                for store_id in store_ids_by_product[product.product_id]
                if store_id in stores_by_id
            ),
        )
        for product in products_by_public_id.values()
    ]


def _candidate_store_context(
    store: Store,
    product_ids: list[str],
    *,
    distance_from_hotel_km: float | None = None,
    airport_match: bool = False,
    terminal_match: bool = False,
    has_wishlist_items: bool = False,
) -> CandidateStoreContext:
    return CandidateStoreContext(
        store_id=store.id,
        name=store.name,
        country=store.country,
        city=store.city,
        type=store.type,
        airport_code=store.airport_code,
        product_ids=product_ids,
        address=store.address,
        latitude=store.latitude,
        longitude=store.longitude,
        terminal=store.terminal,
        opening_hours=store.opening_hours,
        distance_from_hotel_km=distance_from_hotel_km,
        airport_match=airport_match,
        terminal_match=terminal_match,
        has_wishlist_items=has_wishlist_items,
    )


def _flight_context(flight: Flight | None) -> FlightContext | None:
    if flight is None:
        return None
    return FlightContext(
        departure_airport=flight.departure_airport,
        arrival_airport=flight.arrival_airport,
        terminal=flight.terminal,
        departure_at=flight.departure_at,
        arrival_at=flight.arrival_at,
        airport_arrival_at=flight.airport_arrival_at,
    )


def _all_flight_airports(flight: Flight | None) -> set[str]:
    if flight is None:
        return set()
    return {
        airport_code
        for airport_code in (flight.departure_airport, flight.arrival_airport)
        if airport_code is not None
    }


def _trip_store_sort_key(candidate: _TripStoreCandidate) -> tuple[int, int, float, str]:
    priority = (
        0
        if candidate.near_hotel
        else 1
        if candidate.airport_match
        else 2
        if candidate.has_wishlist_items
        else 3
    )
    return (
        priority,
        0 if candidate.terminal_match else 1,
        candidate.distance_from_hotel_km
        if candidate.distance_from_hotel_km is not None
        else float("inf"),
        str(candidate.store.id),
    )


def _normalize_terminal(value: str) -> str:
    return "".join(value.upper().split())


def _product_description(product: Product) -> str | None:
    description = product.metadata_json.get("description")
    return description if isinstance(description, str) else None
