from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FetchedExchangeRate:
    target_currency: str
    rate: Decimal
    rate_date: date


class ExchangeRateProviderError(RuntimeError):
    """Raised when an exchange-rate provider cannot return a valid rate pair."""


class ExchangeRateProvider(Protocol):
    def fetch_rates(self) -> tuple[FetchedExchangeRate, FetchedExchangeRate]: ...
