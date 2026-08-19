from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models.product import Product
from app.services.exchange_rates import ExchangeRateService, ExchangeRateUnavailableError


@dataclass(frozen=True, slots=True)
class PriceQuote:
    retail_price_krw: int
    estimated_refund_krw: int
    estimated_refund_price_krw: int
    converted_retail_price: Decimal | None
    converted_estimated_refund: Decimal | None
    converted_estimated_refund_price: Decimal | None
    converted_amount: Decimal | None
    converted_currency: str
    instant_refund_eligible: bool


class PricingService:
    # Product-card context only knows an individual product price. This is a potential
    # eligibility hint; purchase cumulative limits are evaluated with transaction data.
    _INSTANT_REFUND_TRANSACTION_LIMIT_KRW = 1_000_000

    def __init__(self, exchange_rates: ExchangeRateService) -> None:
        self._exchange_rates = exchange_rates

    def quote(self, product: Product, currency: str) -> PriceQuote:
        estimated_refund_krw = product.estimated_refund_krw
        estimated_refund_price_krw = product.retail_price_krw - estimated_refund_krw
        try:
            fx_rate = self._exchange_rates.get_cached_rate(currency).rate
        except ExchangeRateUnavailableError:
            converted_retail_price = None
            converted_estimated_refund = None
            converted_estimated_refund_price = None
        else:
            converted_retail_price = _convert(product.retail_price_krw, fx_rate)
            converted_estimated_refund = _convert(estimated_refund_krw, fx_rate)
            converted_estimated_refund_price = _convert(
                estimated_refund_price_krw,
                fx_rate,
            )

        return PriceQuote(
            retail_price_krw=product.retail_price_krw,
            estimated_refund_krw=estimated_refund_krw,
            estimated_refund_price_krw=estimated_refund_price_krw,
            converted_retail_price=converted_retail_price,
            converted_estimated_refund=converted_estimated_refund,
            converted_estimated_refund_price=converted_estimated_refund_price,
            converted_amount=converted_estimated_refund_price,
            converted_currency=currency,
            instant_refund_eligible=(
                product.tax_refund_supported
                and product.retail_price_krw < self._INSTANT_REFUND_TRANSACTION_LIMIT_KRW
            ),
        )


def _convert(amount_krw: int, rate: Decimal) -> Decimal:
    return (Decimal(amount_krw) * rate).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
