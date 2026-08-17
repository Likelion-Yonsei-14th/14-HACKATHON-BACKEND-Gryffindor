from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.currency_rate import CurrencyRate

BASE_CURRENCY = "KRW"
TARGET_CURRENCIES = ("USD", "CNY")


class CurrencyRateRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_supported(self) -> list[CurrencyRate]:
        statement = (
            select(CurrencyRate)
            .where(
                CurrencyRate.base_currency == BASE_CURRENCY,
                CurrencyRate.target_currency.in_(TARGET_CURRENCIES),
            )
            .order_by(CurrencyRate.target_currency)
        )
        return list(self._db.scalars(statement).all())

    def save(
        self,
        *,
        target_currency: str,
        rate: Decimal,
        rate_date: date,
        last_checked_at: datetime,
    ) -> CurrencyRate:
        currency_rate = self._db.get(CurrencyRate, (BASE_CURRENCY, target_currency))
        if currency_rate is None:
            currency_rate = CurrencyRate(
                base_currency=BASE_CURRENCY,
                target_currency=target_currency,
                rate=rate,
                rate_date=rate_date,
                last_checked_at=last_checked_at,
            )
            self._db.add(currency_rate)
        else:
            currency_rate.rate = rate
            currency_rate.rate_date = rate_date
            currency_rate.last_checked_at = last_checked_at
        return currency_rate

    def mark_checked(self, rates: list[CurrencyRate], checked_at: datetime) -> None:
        for rate in rates:
            rate.last_checked_at = checked_at
