from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, CheckConstraint, Date, DateTime, Numeric, PrimaryKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utc_now


class CurrencyRate(Base):
    __tablename__ = "currency_rates"
    __table_args__ = (
        PrimaryKeyConstraint(
            "base_currency",
            "target_currency",
            name="pk_currency_rates",
        ),
        CheckConstraint(
            "base_currency = 'KRW'",
            name="ck_currency_rates_base_krw",
        ),
        CheckConstraint(
            "target_currency IN ('USD', 'CNY')",
            name="ck_currency_rates_target_supported",
        ),
        CheckConstraint("rate > 0", name="ck_currency_rates_rate_positive"),
    )

    base_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    target_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
