from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models.product import Product


@dataclass(frozen=True, slots=True)
class PriceQuote:
    retail_price_krw: int
    estimated_refund_krw: int
    estimated_refund_price_krw: int
    converted_amount: Decimal
    converted_currency: str
    instant_refund_eligible: bool


class MockPricingService:
    _REFUND_RATE = Decimal("0.055")
    _INSTANT_REFUND_LIMIT_KRW = 5_000_000
    _FX_RATES = {
        "CNY": Decimal("0.00505859"),
        "USD": Decimal("0.00072718"),
        "JPY": Decimal("0.10791"),
        "EUR": Decimal("0.000625"),
    }

    def quote(self, product: Product, currency: str) -> PriceQuote:
        estimated_refund_krw = self._estimated_refund(product)
        estimated_refund_price_krw = product.retail_price_krw - estimated_refund_krw
        fx_rate = self._FX_RATES.get(currency, Decimal("1"))
        converted_amount = (Decimal(estimated_refund_price_krw) * fx_rate).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        return PriceQuote(
            retail_price_krw=product.retail_price_krw,
            estimated_refund_krw=estimated_refund_krw,
            estimated_refund_price_krw=estimated_refund_price_krw,
            converted_amount=converted_amount,
            converted_currency=currency,
            instant_refund_eligible=(
                product.tax_refund_supported
                and product.retail_price_krw <= self._INSTANT_REFUND_LIMIT_KRW
            ),
        )

    def _estimated_refund(self, product: Product) -> int:
        if not product.tax_refund_supported:
            return 0

        refund_in_thousands = (
            Decimal(product.retail_price_krw) * self._REFUND_RATE / Decimal(1000)
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(refund_in_thousands * 1000)
