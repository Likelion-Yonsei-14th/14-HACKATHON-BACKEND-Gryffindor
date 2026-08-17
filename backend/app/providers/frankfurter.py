from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast

import httpx

from app.providers.exchange_rates import (
    ExchangeRateProviderError,
    FetchedExchangeRate,
)

BASE_CURRENCY = "KRW"
TARGET_CURRENCIES = ("USD", "CNY")


class FrankfurterExchangeRateProvider:
    def __init__(
        self,
        *,
        base_url: str = "https://api.frankfurter.dev/v2",
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    def fetch_rates(self) -> tuple[FetchedExchangeRate, FetchedExchangeRate]:
        try:
            response = self._request_rates()
            response.raise_for_status()
            payload: object = response.json()
            return _parse_rates(payload)
        except (httpx.HTTPError, ValueError, TypeError, InvalidOperation) as exc:
            raise ExchangeRateProviderError(
                "Frankfurter did not return valid KRW rates for USD and CNY."
            ) from exc

    def _request_rates(self) -> httpx.Response:
        params = {"base": BASE_CURRENCY, "quotes": ",".join(TARGET_CURRENCIES)}
        if self._client is not None:
            return self._client.get(f"{self._base_url}/rates", params=params)

        with httpx.Client(timeout=self._timeout_seconds) as client:
            return client.get(f"{self._base_url}/rates", params=params)


def _parse_rates(payload: object) -> tuple[FetchedExchangeRate, FetchedExchangeRate]:
    if not isinstance(payload, list):
        raise ValueError("Frankfurter response must be a list")

    rates_by_target: dict[str, FetchedExchangeRate] = {}
    for item in cast(list[object], payload):
        if not isinstance(item, dict):
            raise ValueError("Frankfurter rate entry must be an object")
        item_data = cast(dict[str, object], item)

        base_currency = item_data.get("base")
        target_currency = item_data.get("quote")
        raw_rate = item_data.get("rate")
        raw_date = item_data.get("date")
        if base_currency != BASE_CURRENCY or target_currency not in TARGET_CURRENCIES:
            raise ValueError("Frankfurter returned an unsupported currency pair")
        if target_currency in rates_by_target:
            raise ValueError("Frankfurter returned a duplicate currency pair")
        if not isinstance(raw_date, str):
            raise ValueError("Frankfurter returned an invalid rate date")

        rate = Decimal(str(raw_rate))
        if not rate.is_finite() or rate <= 0:
            raise ValueError("Frankfurter returned a non-positive rate")

        rates_by_target[target_currency] = FetchedExchangeRate(
            target_currency=target_currency,
            rate=rate,
            rate_date=date.fromisoformat(raw_date),
        )

    if set(rates_by_target) != set(TARGET_CURRENCIES):
        raise ValueError("Frankfurter response is missing USD or CNY")

    return rates_by_target["USD"], rates_by_target["CNY"]
