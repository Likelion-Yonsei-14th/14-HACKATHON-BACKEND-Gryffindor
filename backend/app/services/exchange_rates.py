import logging
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock

from sqlalchemy.orm import Session

from app.models.common import utc_now
from app.models.currency_rate import CurrencyRate
from app.providers.exchange_rates import ExchangeRateProvider, ExchangeRateProviderError
from app.repositories.currency_rates import CurrencyRateRepository

BASE_CURRENCY = "KRW"
TARGET_CURRENCIES = ("USD", "CNY")

logger = logging.getLogger(__name__)
_refresh_lock = Lock()


class UnsupportedCurrencyError(ValueError):
    """Raised when a currency other than USD or CNY is requested."""


class ExchangeRateUnavailableError(RuntimeError):
    """Raised when neither Frankfurter nor a complete DB cache can provide rates."""


class ExchangeRateService:
    def __init__(
        self,
        db: Session,
        provider: ExchangeRateProvider | None = None,
        *,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._db = db
        self._provider = provider
        self._rates = CurrencyRateRepository(db)
        self._now = now

    def get_rates(self) -> tuple[CurrencyRate, CurrencyRate]:
        checked_at = _as_utc(self._now())
        cached_rates = self._rates.list_supported()
        if _is_complete(cached_rates) and _checked_today(cached_rates, checked_at):
            return _ordered(cached_rates)

        with _refresh_lock:
            cached_rates = self._rates.list_supported()
            if _is_complete(cached_rates) and _checked_today(cached_rates, checked_at):
                return _ordered(cached_rates)
            return self._refresh_or_fallback(cached_rates, checked_at)

    def get_rate(self, target_currency: str) -> CurrencyRate:
        normalized_currency = target_currency.upper()
        _validate_target_currency(normalized_currency)
        return next(
            rate
            for rate in self.get_rates()
            if rate.target_currency == normalized_currency
        )

    def get_cached_rate(self, target_currency: str) -> CurrencyRate:
        """Read a cached rate without refreshing it through the external provider."""
        normalized_currency = target_currency.upper()
        _validate_target_currency(normalized_currency)
        cached_rate = next(
            (
                rate
                for rate in self._rates.list_supported()
                if rate.target_currency == normalized_currency
            ),
            None,
        )
        if cached_rate is None:
            raise ExchangeRateUnavailableError(
                f"The cached KRW/{normalized_currency} exchange rate is unavailable."
            )
        return cached_rate

    def _refresh_or_fallback(
        self,
        cached_rates: list[CurrencyRate],
        checked_at: datetime,
    ) -> tuple[CurrencyRate, CurrencyRate]:
        if self._provider is None:
            raise ExchangeRateUnavailableError(
                "An exchange-rate provider is required to refresh the cache."
            )
        try:
            fetched_rates = self._provider.fetch_rates()
        except ExchangeRateProviderError as exc:
            if not _is_complete(cached_rates):
                raise ExchangeRateUnavailableError(
                    "Exchange rates are unavailable and the DB cache is incomplete."
                ) from exc

            self._rates.mark_checked(cached_rates, checked_at)
            self._db.commit()
            logger.warning("exchange_rate_refresh_failed_using_cached_rates", exc_info=True)
            return _ordered(cached_rates)

        if {rate.target_currency for rate in fetched_rates} != set(TARGET_CURRENCIES):
            raise ExchangeRateUnavailableError(
                "The exchange-rate provider returned an invalid pair."
            )

        saved_rates = [
            self._rates.save(
                target_currency=rate.target_currency,
                rate=rate.rate,
                rate_date=rate.rate_date,
                last_checked_at=checked_at,
            )
            for rate in fetched_rates
        ]
        self._db.commit()
        return _ordered(saved_rates)


def _is_complete(rates: list[CurrencyRate]) -> bool:
    return {rate.target_currency for rate in rates} == set(TARGET_CURRENCIES)


def _checked_today(rates: list[CurrencyRate], now: datetime) -> bool:
    return all(rate.last_checked_at.date() == now.date() for rate in rates)


def _ordered(rates: list[CurrencyRate]) -> tuple[CurrencyRate, CurrencyRate]:
    rates_by_target = {rate.target_currency: rate for rate in rates}
    return rates_by_target["USD"], rates_by_target["CNY"]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _validate_target_currency(target_currency: str) -> None:
    if target_currency not in TARGET_CURRENCIES:
        raise UnsupportedCurrencyError("Only USD and CNY exchange rates are supported.")
