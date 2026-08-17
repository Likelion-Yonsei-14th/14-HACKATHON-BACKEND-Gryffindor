from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import utc_now

if TYPE_CHECKING:
    from app.models.shopping import SessionProduct


json_type = JSON().with_variant(JSONB(), "postgresql")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "price_krw >= 0",
            name="ck_products_price_nonnegative",
        ),
        CheckConstraint(
            "estimated_refund_krw >= 0",
            name="ck_products_estimated_refund_nonnegative",
        ),
        CheckConstraint(
            "estimated_refund_krw <= price_krw",
            name="ck_products_estimated_refund_not_above_price",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    brand: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    # Keep the Python attribute/API terminology stable while storing the policy name in DB.
    retail_price_krw: Mapped[int] = mapped_column("price_krw", BigInteger, nullable=False)
    estimated_refund_krw: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_refund_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        json_type,
        nullable=False,
        default=dict,
    )
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

    session_products: Mapped[list[SessionProduct]] = relationship(back_populates="product")
