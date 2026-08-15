from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain.enums import TriggerType
from app.models.shopping import SessionProduct, ShoppingSession


class ShoppingSessionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, shopping_session: ShoppingSession) -> ShoppingSession:
        self._db.add(shopping_session)
        self._db.flush()
        return shopping_session

    def get(self, session_id: UUID) -> ShoppingSession | None:
        return self._db.get(ShoppingSession, session_id)


class SessionProductRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def upsert_observation(
        self,
        *,
        session_id: UUID,
        product_id: UUID,
        captured_at: datetime,
        trigger_type: TriggerType,
        occupancy_ratio: Decimal,
        dwell_ms: int,
    ) -> tuple[SessionProduct, bool]:
        statement = select(SessionProduct).where(
            SessionProduct.session_id == session_id,
            SessionProduct.product_id == product_id,
        )
        session_product = self._db.scalar(statement)

        if session_product is None:
            normalized_captured_at = _as_utc(captured_at)
            session_product = SessionProduct(
                session_id=session_id,
                product_id=product_id,
                first_observed_at=normalized_captured_at,
                last_observed_at=normalized_captured_at,
                max_occupancy_ratio=occupancy_ratio,
                max_dwell_ms=dwell_ms,
                last_trigger_type=trigger_type,
            )
            self._db.add(session_product)
            self._db.flush()
            return session_product, True

        normalized_captured_at = _as_utc(captured_at)
        session_product.first_observed_at = min(
            _as_utc(session_product.first_observed_at),
            normalized_captured_at,
        )
        session_product.last_observed_at = max(
            _as_utc(session_product.last_observed_at),
            normalized_captured_at,
        )
        session_product.max_occupancy_ratio = max(
            session_product.max_occupancy_ratio,
            occupancy_ratio,
        )
        session_product.max_dwell_ms = max(session_product.max_dwell_ms, dwell_ms)
        session_product.last_trigger_type = trigger_type
        session_product.observation_count += 1
        self._db.flush()
        return session_product, False

    def list_for_session(self, session_id: UUID) -> list[SessionProduct]:
        statement = (
            select(SessionProduct)
            .options(joinedload(SessionProduct.product))
            .where(SessionProduct.session_id == session_id)
            .order_by(SessionProduct.first_observed_at)
        )
        return list(self._db.scalars(statement).all())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
