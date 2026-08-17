from decimal import Decimal

import httpx
import pytest

from app.providers.exchange_rates import ExchangeRateProviderError
from app.providers.frankfurter import FrankfurterExchangeRateProvider


def test_frankfurter_fetches_usd_and_cny_in_one_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {"date": "2026-08-17", "base": "KRW", "quote": "CNY", "rate": 0.00476},
                {"date": "2026-08-17", "base": "KRW", "quote": "USD", "rate": 0.00071},
            ],
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        usd_rate, cny_rate = FrankfurterExchangeRateProvider(
            base_url="https://frankfurter.test/v2",
            client=client,
        ).fetch_rates()

    assert len(requests) == 1
    assert requests[0].url.path == "/v2/rates"
    assert requests[0].url.params["base"] == "KRW"
    assert requests[0].url.params["quotes"] == "USD,CNY"
    assert usd_rate.target_currency == "USD"
    assert usd_rate.rate == Decimal("0.00071")
    assert cny_rate.target_currency == "CNY"
    assert cny_rate.rate == Decimal("0.00476")
    assert usd_rate.rate_date.isoformat() == "2026-08-17"


def test_frankfurter_rejects_incomplete_rate_pair() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"date": "2026-08-17", "base": "KRW", "quote": "USD", "rate": 0.00071}
            ],
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = FrankfurterExchangeRateProvider(client=client)
        with pytest.raises(ExchangeRateProviderError):
            provider.fetch_rates()


def test_frankfurter_maps_http_failure_to_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = FrankfurterExchangeRateProvider(client=client)
        with pytest.raises(ExchangeRateProviderError):
            provider.fetch_rates()
