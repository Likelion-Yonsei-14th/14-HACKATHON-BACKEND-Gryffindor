from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import DEMO_USER_ID
from app.domain.enums import PurchaseState, RecognitionStatus, SessionStatus, TriggerType
from app.errors import AppError
from app.models.common import utc_now
from app.models.personalization import WishlistItem
from app.models.product import Product
from app.models.shopping import SessionProduct, ShoppingSession
from app.providers.recognition import (
    RecognitionCandidate,
    RecognitionProvider,
    RecognitionProviderError,
    RecognitionTelemetry,
)
from app.repositories.personalization import PersonalizationRepository
from app.repositories.products import ProductRepository
from app.repositories.shopping import SessionProductRepository, ShoppingSessionRepository
from app.repositories.stores import StoreRepository
from app.services.exchange_rates import ExchangeRateService
from app.services.pricing import PriceQuote, PricingService


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    status: RecognitionStatus
    candidate_product_ids: tuple[str, ...] = ()
    is_new: bool | None = None
    product: Product | None = None
    session_product: SessionProduct | None = None
    pricing: PriceQuote | None = None
    telemetry: RecognitionTelemetry | None = None


class ShoppingSessionService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._sessions = ShoppingSessionRepository(db)
        self._session_products = SessionProductRepository(db)
        self._stores = StoreRepository(db)
        self._pricing = PricingService(ExchangeRateService(db))

    def create(self, currency: str, store_id: UUID) -> ShoppingSession:
        store = self._stores.get_active(store_id)
        if store is None:
            raise AppError(404, "STORE_NOT_FOUND", "Store was not found.")
        shopping_session = self._sessions.add(ShoppingSession(currency=currency, store_id=store.id))
        self._db.commit()
        return shopping_session

    def complete(self, session_id: UUID) -> ShoppingSession:
        shopping_session = self.get(session_id)
        if shopping_session.status is SessionStatus.ACTIVE:
            shopping_session.status = SessionStatus.COMPLETED
            shopping_session.completed_at = utc_now()
            self._db.commit()
        return shopping_session

    def list_products(self, session_id: UUID) -> tuple[ShoppingSession, list[SessionProduct]]:
        shopping_session = self.get(session_id)
        return shopping_session, self._session_products.list_for_session(session_id)

    def price_for(self, product: Product, currency: str) -> PriceQuote:
        return self._pricing.quote(product, currency)

    def get(self, session_id: UUID) -> ShoppingSession:
        shopping_session = self._sessions.get(session_id)
        if shopping_session is None:
            raise AppError(404, "SESSION_NOT_FOUND", "Shopping session was not found.")
        return shopping_session

    def submit_review(
        self,
        session_id: UUID,
        purchased_product_ids: list[str],
        interested_product_ids: list[str],
    ) -> tuple[list[str], list[str]]:
        """Apply review selections to session products, add interested to wishlist."""
        shopping_session = self.get(session_id)
        session_products = self._session_products.list_for_session(session_id)

        # Build lookup: public product_id → SessionProduct
        sp_by_product_id: dict[str, SessionProduct] = {
            sp.product.product_id: sp for sp in session_products
        }

        # Validate all incoming IDs exist in this session
        all_requested = set(purchased_product_ids) | set(interested_product_ids)
        invalid_ids = all_requested - set(sp_by_product_id.keys())
        if invalid_ids:
            raise AppError(
                422,
                "INVALID_PRODUCT_IDS",
                f"Product IDs not found in this session: {sorted(invalid_ids)}",
            )

        # Enforce mutual exclusivity: purchased wins over interested
        purchased_set = set(purchased_product_ids)
        interested_set = set(interested_product_ids) - purchased_set

        # Reset all, then apply selections
        for product_id, sp in sp_by_product_id.items():
            if product_id in purchased_set:
                sp.purchase_state = PurchaseState.PURCHASED
                sp.interested = False
            elif product_id in interested_set:
                sp.purchase_state = PurchaseState.UNSET
                sp.interested = True
            else:
                sp.purchase_state = PurchaseState.UNSET
                sp.interested = False

        # Add interested products to wishlist
        personalization = PersonalizationRepository(self._db)
        for product_id in interested_set:
            sp = sp_by_product_id[product_id]
            existing = personalization.get_wishlist_item(
                shopping_session.user_id, sp.product_id
            )
            if existing is None:
                personalization.add_wishlist_item(
                    WishlistItem(
                        user_id=shopping_session.user_id,
                        product_id=sp.product_id,
                    )
                )
                try:
                    self._db.flush()
                except IntegrityError:
                    self._db.rollback()

        self._db.commit()

        # Return the final state
        final_purchased = sorted(
            pid for pid, sp in sp_by_product_id.items()
            if sp.purchase_state == PurchaseState.PURCHASED
        )
        final_interested = sorted(
            pid for pid, sp in sp_by_product_id.items()
            if sp.interested
        )
        return final_purchased, final_interested


class RecognitionService:
    def __init__(
        self,
        db: Session,
        provider: RecognitionProvider,
        pricing: PricingService | None = None,
        candidate_limit: int = 20,
    ) -> None:
        self._db = db
        self._provider = provider
        self._pricing = pricing or PricingService(ExchangeRateService(db))
        self._candidate_limit = candidate_limit
        self._sessions = ShoppingSessionRepository(db)
        self._products = ProductRepository(db)
        self._session_products = SessionProductRepository(db)

    async def recognize(
        self,
        *,
        session_id: UUID,
        image_bytes: bytes,
        captured_at: datetime,
        trigger_type: TriggerType,
        occupancy_ratio: float,
        dwell_ms: int,
    ) -> RecognitionResult:
        shopping_session = self._get_active_session(session_id)
        products = [
            product
            for product in self._products.list_all()
            if product.metadata_json.get("recognitionTest") is True
        ][: self._candidate_limit]
        products_by_product_id = {product.product_id: product for product in products}
        candidates = [
            RecognitionCandidate(
                product_id=product.product_id,
                sku=product.sku,
                brand=product.brand,
                name=product.name,
                category=product.category,
                reference_image_url=product.image_url,
            )
            for product in products
        ]

        try:
            decision = await self._provider.recognize(image_bytes, candidates)
        except RecognitionProviderError as exc:
            raise AppError(
                503,
                "RECOGNITION_PROVIDER_ERROR",
                "The recognition provider is temporarily unavailable.",
            ) from exc

        if decision.status is RecognitionStatus.UNKNOWN:
            return RecognitionResult(status=RecognitionStatus.UNKNOWN, telemetry=decision.telemetry)

        if decision.status is RecognitionStatus.AMBIGUOUS:
            candidate_product_ids = _allowed_candidate_ids(
                decision.candidate_product_ids,
                products_by_product_id,
            )
            if len(candidate_product_ids) < 2:
                return RecognitionResult(
                    status=RecognitionStatus.UNKNOWN,
                    telemetry=decision.telemetry,
                )
            return RecognitionResult(
                status=RecognitionStatus.AMBIGUOUS,
                candidate_product_ids=candidate_product_ids,
                telemetry=decision.telemetry,
            )

        product = products_by_product_id.get(decision.product_id or "")
        if product is None:
            return RecognitionResult(status=RecognitionStatus.UNKNOWN)

        session_product, is_new = self._session_products.upsert_observation(
            session_id=shopping_session.id,
            product_id=product.id,
            captured_at=captured_at,
            trigger_type=trigger_type,
            occupancy_ratio=Decimal(str(occupancy_ratio)),
            dwell_ms=dwell_ms,
        )
        quote = self._pricing.quote(product, shopping_session.currency)
        self._db.commit()
        return RecognitionResult(
            status=RecognitionStatus.MATCHED,
            is_new=is_new,
            product=product,
            session_product=session_product,
            pricing=quote,
            telemetry=decision.telemetry,
        )

    def _get_active_session(self, session_id: UUID) -> ShoppingSession:
        shopping_session = self._sessions.get(session_id)
        if shopping_session is None:
            raise AppError(404, "SESSION_NOT_FOUND", "Shopping session was not found.")
        if shopping_session.status is not SessionStatus.ACTIVE:
            raise AppError(
                409,
                "SESSION_NOT_ACTIVE",
                "Recognition is allowed only for an active shopping session.",
            )
        return shopping_session


def _allowed_candidate_ids(
    candidate_product_ids: tuple[str, ...],
    products_by_product_id: dict[str, Product],
) -> tuple[str, ...]:
    allowed_ids: list[str] = []
    for product_id in candidate_product_ids:
        if product_id in products_by_product_id and product_id not in allowed_ids:
            allowed_ids.append(product_id)
    return tuple(allowed_ids)
