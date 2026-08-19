import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.constants import DEMO_USER_ID
from app.errors import AppError
from app.models.product import Product
from app.models.store import Store
from app.providers.recommendation import (
    CandidateProductContext,
    CandidateStoreContext,
    FlightContext,
    PurchasedProductContext,
    RecommendationContext,
    RecommendationProvider,
    RecommendationProviderError,
    ViewedProductContext,
)
from app.repositories.personalization import PersonalizationRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RecommendedProduct:
    product: Product
    reason: str


@dataclass(frozen=True, slots=True)
class RecommendedStore:
    store: Store
    reason: str
    products: tuple[RecommendedProduct, ...]


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    stores: tuple[RecommendedStore, ...]


@dataclass(slots=True)
class _ViewedAggregate:
    observation_count: int = 0
    max_dwell_ms: int = 0
    store_ids: set[UUID] = field(default_factory=lambda: set[UUID]())


@dataclass(frozen=True, slots=True)
class BuiltRecommendationContext:
    context: RecommendationContext
    stores_by_id: dict[UUID, Store]
    products_by_public_id: dict[str, Product]
    product_ids_by_store: dict[UUID, frozenset[str]]


class RecommendationContextBuilder:
    def __init__(self, db: Session, *, candidate_limit: int = 50) -> None:
        self._repository = PersonalizationRepository(db)
        self._candidate_limit = candidate_limit

    def build(self) -> BuiltRecommendationContext:
        if self._repository.get_user(DEMO_USER_ID) is None:
            raise AppError(500, "DEMO_USER_NOT_CONFIGURED", "The demo user is not configured.")
        wishlist_items = self._repository.list_wishlist(DEMO_USER_ID)
        wishlist_ids = [item.product.product_id for item in wishlist_items]

        receipts = self._repository.list_receipts(DEMO_USER_ID)
        purchased_ids = sorted(
            {
                item.product.product_id
                for receipt in receipts
                for item in receipt.items
                if item.product is not None
            }
        )
        purchased_id_set = set(purchased_ids)
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
            aggregate.max_dwell_ms = max(
                aggregate.max_dwell_ms,
                session_product.max_dwell_ms,
            )
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

        latest_flight = self._repository.latest_flight(DEMO_USER_ID)
        flight_context = (
            FlightContext(
                departure_airport=latest_flight.departure_airport,
                arrival_airport=latest_flight.arrival_airport,
                terminal=latest_flight.terminal,
                departure_at=latest_flight.departure_at,
                arrival_at=latest_flight.arrival_at,
                airport_arrival_at=latest_flight.airport_arrival_at,
            )
            if latest_flight is not None
            else None
        )

        stores = self._repository.list_candidate_stores()
        candidates_by_id: dict[str, Product] = {}
        store_ids_by_product: dict[str, set[UUID]] = {}
        for store in stores:
            for store_product in store.store_products:
                product = store_product.product
                if product.product_id in purchased_id_set:
                    continue
                candidates_by_id[product.product_id] = product
                store_ids_by_product.setdefault(product.product_id, set()).add(store.id)

        wishlist_id_set = set(wishlist_ids)
        viewed_id_set = set(viewed_aggregates)
        prioritized_product_ids = sorted(
            candidates_by_id,
            key=lambda product_id: (
                0 if product_id in wishlist_id_set else 1 if product_id in viewed_id_set else 2,
                product_id,
            ),
        )[: self._candidate_limit]
        selected_product_ids = set(prioritized_product_ids)
        products_by_public_id = {
            product_id: candidates_by_id[product_id] for product_id in prioritized_product_ids
        }

        airport_codes: set[str] = (
            {
                airport_code
                for airport_code in (
                    latest_flight.departure_airport,
                    latest_flight.arrival_airport,
                )
                if airport_code is not None
            }
            if latest_flight is not None
            else set()
        )
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
            candidate_stores.append(
                CandidateStoreContext(
                    store_id=store.id,
                    name=store.name,
                    country=store.country,
                    city=store.city,
                    type=store.type,
                    airport_code=store.airport_code,
                    product_ids=product_ids,
                )
            )
            stores_by_id[store.id] = store
            product_ids_by_store[store.id] = frozenset(product_ids)

        candidate_products = [
            CandidateProductContext(
                product_id=product.product_id,
                sku=product.sku,
                brand=product.brand,
                name=product.name,
                category=product.category,
                store_ids=sorted(
                    store_id
                    for store_id in store_ids_by_product[product.product_id]
                    if store_id in stores_by_id
                ),
            )
            for product in products_by_public_id.values()
        ]

        return BuiltRecommendationContext(
            context=RecommendationContext(
                wishlist_product_ids=wishlist_ids,
                viewed_products=viewed_products,
                purchased_product_ids=purchased_ids,
                purchased_products=purchased_products,
                latest_flight=flight_context,
                candidate_stores=candidate_stores,
                candidate_products=candidate_products,
            ),
            stores_by_id=stores_by_id,
            products_by_public_id=products_by_public_id,
            product_ids_by_store=product_ids_by_store,
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
        built = self._builder.build()
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
                )
            )

        if invalid_items:
            logger.warning(
                "recommendation_validation_failed invalid_items=%d",
                invalid_items,
            )
        return RecommendationResult(stores=tuple(recommended_stores)), built.context
