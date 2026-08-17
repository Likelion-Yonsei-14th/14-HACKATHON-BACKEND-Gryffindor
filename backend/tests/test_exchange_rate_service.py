from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.currency_rate import CurrencyRate
from app.providers.exchange_rates import (
    ExchangeRateProviderError,
    FetchedExchangeRate,
)
from app.services.exchange_rates import (
    ExchangeRateService,
    ExchangeRateUnavailableError,
    UnsupportedCurrencyError,
)


class FakeExchangeRateProvider:
    def __init__(
        self,
        responses: list[tuple[FetchedExchangeRate, FetchedExchangeRate]] | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        self._responses = responses or []
        self._unavailable = unavailable
        self.calls = 0

    def fetch_rates(self) -> tuple[FetchedExchangeRate, FetchedExchangeRate]:
        self.calls += 1
        if self._unavailable:
            raise ExchangeRateProviderError("provider unavailable")
        return self._responses.pop(0)

    def recover_with(
        self,
        response: tuple[FetchedExchangeRate, FetchedExchangeRate],
    ) -> None:
        self._unavailable = False
        self._responses.append(response)


def _pair(
    *,
    rate_date: date,
    usd: str = "0.00071",
    cny: str = "0.00476",
) -> tuple[FetchedExchangeRate, FetchedExchangeRate]:
    return (
        FetchedExchangeRate("USD", Decimal(usd), rate_date),
        FetchedExchangeRate("CNY", Decimal(cny), rate_date),
    )


def test_service_persists_both_rates_and_skips_repeat_check_today(
    db_session: Session,
) -> None:
    checked_at = datetime(2026, 8, 17, 1, 30, tzinfo=UTC)
    provider = FakeExchangeRateProvider([_pair(rate_date=date(2026, 8, 17))])
    service = ExchangeRateService(db_session, provider, now=lambda: checked_at)

    first_rates = service.get_rates()
    second_rates = service.get_rates()

    assert provider.calls == 1
    assert [rate.target_currency for rate in first_rates] == ["USD", "CNY"]
    assert [rate.target_currency for rate in second_rates] == ["USD", "CNY"]
    stored_rates = list(db_session.scalars(select(CurrencyRate)).all())
    assert len(stored_rates) == 2
    assert {rate.base_currency for rate in stored_rates} == {"KRW"}
    assert {rate.last_checked_at for rate in stored_rates} == {checked_at}


def test_old_rate_date_does_not_repeat_check_on_weekend(db_session: Session) -> None:
    sunday = datetime(2026, 8, 16, 3, 0, tzinfo=UTC)
    friday = date(2026, 8, 14)
    provider = FakeExchangeRateProvider([_pair(rate_date=friday)])
    service = ExchangeRateService(db_session, provider, now=lambda: sunday)

    first_rates = service.get_rates()
    second_rates = service.get_rates()

    assert provider.calls == 1
    assert {rate.rate_date for rate in first_rates} == {friday}
    assert {rate.rate_date for rate in second_rates} == {friday}
    assert {rate.last_checked_at for rate in second_rates} == {sunday}


def test_service_refreshes_on_first_use_next_day(db_session: Session) -> None:
    current_time = [datetime(2026, 8, 17, 1, 0, tzinfo=UTC)]
    provider = FakeExchangeRateProvider(
        [
            _pair(rate_date=date(2026, 8, 17)),
            _pair(rate_date=date(2026, 8, 18), usd="0.00072", cny="0.00477"),
        ]
    )
    service = ExchangeRateService(db_session, provider, now=lambda: current_time[0])

    service.get_rates()
    current_time[0] = datetime(2026, 8, 18, 0, 1, tzinfo=UTC)
    usd_rate, cny_rate = service.get_rates()

    assert provider.calls == 2
    assert usd_rate.rate == Decimal("0.00072")
    assert cny_rate.rate == Decimal("0.00477")
    assert usd_rate.rate_date == date(2026, 8, 18)


def test_provider_failure_uses_cache_and_marks_today_checked(db_session: Session) -> None:
    first_day = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)
    ExchangeRateService(
        db_session,
        FakeExchangeRateProvider([_pair(rate_date=first_day.date())]),
        now=lambda: first_day,
    ).get_rates()
    next_day = datetime(2026, 8, 18, 2, 0, tzinfo=UTC)
    unavailable_provider = FakeExchangeRateProvider(unavailable=True)
    service = ExchangeRateService(
        db_session,
        unavailable_provider,
        now=lambda: next_day,
    )

    fallback_rates = service.get_rates()
    repeated_rates = service.get_rates()

    assert unavailable_provider.calls == 1
    assert {rate.rate_date for rate in fallback_rates} == {first_day.date()}
    assert {rate.last_checked_at for rate in repeated_rates} == {next_day}


def test_provider_failure_without_cache_is_unavailable(db_session: Session) -> None:
    service = ExchangeRateService(
        db_session,
        FakeExchangeRateProvider(unavailable=True),
        now=lambda: datetime(2026, 8, 17, tzinfo=UTC),
    )

    with pytest.raises(ExchangeRateUnavailableError):
        service.get_rates()


def test_provider_retries_same_day_after_initial_failure_without_cache(
    db_session: Session,
) -> None:
    checked_at = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)
    provider = FakeExchangeRateProvider(unavailable=True)
    service = ExchangeRateService(db_session, provider, now=lambda: checked_at)

    with pytest.raises(ExchangeRateUnavailableError):
        service.get_rates()

    assert list(db_session.scalars(select(CurrencyRate)).all()) == []
    provider.recover_with(_pair(rate_date=checked_at.date()))

    recovered_rates = service.get_rates()
    cached_rates = service.get_rates()

    assert provider.calls == 2
    assert [rate.target_currency for rate in recovered_rates] == ["USD", "CNY"]
    assert [rate.target_currency for rate in cached_rates] == ["USD", "CNY"]
    assert len(list(db_session.scalars(select(CurrencyRate)).all())) == 2


def test_service_rejects_unsupported_currency_before_fetch(db_session: Session) -> None:
    provider = FakeExchangeRateProvider([_pair(rate_date=date(2026, 8, 17))])
    service = ExchangeRateService(db_session, provider)

    with pytest.raises(UnsupportedCurrencyError):
        service.get_rate("JPY")

    assert provider.calls == 0
