from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import DEMO_USER_ID
from app.db.base import Base
from app.domain.enums import PurchaseState, SessionStatus, TriggerType
from app.models.common import utc_now

if TYPE_CHECKING:
    from app.models.personalization import User
    from app.models.product import Product
    from app.models.store import Store


class ShoppingSession(Base):
    __tablename__ = "shopping_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        default=DEMO_USER_ID,
        server_default=str(DEMO_USER_ID),
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status"),
        nullable=False,
        default=SessionStatus.ACTIVE,
    )
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    session_products: Mapped[list[SessionProduct]] = relationship(
        back_populates="shopping_session",
        cascade="all, delete-orphan",
    )
    store: Mapped[Store] = relationship(back_populates="shopping_sessions")
    user: Mapped[User] = relationship(back_populates="shopping_sessions")


class SessionProduct(Base):
    __tablename__ = "session_products"
    __table_args__ = (
        UniqueConstraint("session_id", "product_id", name="uq_session_products_session_product"),
        CheckConstraint(
            "max_occupancy_ratio >= 0 AND max_occupancy_ratio <= 1",
            name="ck_session_products_occupancy_range",
        ),
        CheckConstraint(
            "max_dwell_ms >= 0",
            name="ck_session_products_dwell_nonnegative",
        ),
        CheckConstraint(
            "observation_count >= 1",
            name="ck_session_products_observation_count_positive",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopping_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_occupancy_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    max_dwell_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    last_trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType, name="trigger_type"),
        nullable=False,
    )
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    purchase_state: Mapped[PurchaseState] = mapped_column(
        Enum(PurchaseState, name="purchase_state"),
        nullable=False,
        default=PurchaseState.UNSET,
    )
    interested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    shopping_session: Mapped[ShoppingSession] = relationship(back_populates="session_products")
    product: Mapped[Product] = relationship(back_populates="session_products")
