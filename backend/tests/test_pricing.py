from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.currency_rate import CurrencyRate
from app.models.product import Product
from app.services.exchange_rates import ExchangeRateService
from app.services.pricing import PricingService


def test_pricing_uses_fixed_refund_and_cached_decimal_rate(db_session: Session) -> None:
    product = Product(
        product_id="mcm_001",
        sku="SKU001",
        brand="MCM",
        name="Product Name",
        category="bag",
        image_url="https://example.com/product.jpg",
        retail_price_krw=1_090_000,
        estimated_refund_krw=76_000,
        tax_refund_supported=True,
    )

    quote = PricingService(ExchangeRateService(db_session)).quote(product, "CNY")

    assert quote.retail_price_krw == 1_090_000
    assert quote.estimated_refund_krw == 76_000
    assert quote.estimated_refund_price_krw == 1_014_000
    assert str(quote.converted_retail_price) == "5513.86"
    assert str(quote.converted_estimated_refund) == "384.45"
    assert str(quote.converted_estimated_refund_price) == "5129.41"
    assert quote.converted_amount == quote.converted_estimated_refund_price
    assert quote.converted_currency == "CNY"
    assert quote.instant_refund_eligible is True


def test_pricing_uses_zero_seed_refund_for_unsupported_product(
    db_session: Session,
) -> None:
    product = Product(
        product_id="mock_unsupported",
        sku="MOCK-UNSUPPORTED",
        brand="Mock",
        name="Unsupported",
        category="other",
        image_url="https://example.com/unsupported.jpg",
        retail_price_krw=100_000,
        estimated_refund_krw=0,
        tax_refund_supported=False,
    )

    quote = PricingService(ExchangeRateService(db_session)).quote(product, "CNY")

    assert quote.estimated_refund_krw == 0
    assert quote.estimated_refund_price_krw == 100_000
    assert quote.instant_refund_eligible is False


def test_pricing_returns_krw_amounts_when_exchange_rate_cache_is_missing(
    db_session: Session,
) -> None:
    db_session.execute(delete(CurrencyRate))
    db_session.commit()
    product = Product(
        product_id="mcm_001",
        sku="SKU001",
        brand="MCM",
        name="Product Name",
        category="bag",
        image_url="https://example.com/product.jpg",
        retail_price_krw=1_090_000,
        estimated_refund_krw=76_000,
        tax_refund_supported=True,
    )

    quote = PricingService(ExchangeRateService(db_session)).quote(product, "CNY")

    assert quote.retail_price_krw == 1_090_000
    assert quote.estimated_refund_krw == 76_000
    assert quote.estimated_refund_price_krw == 1_014_000
    assert quote.converted_retail_price is None
    assert quote.converted_estimated_refund is None
    assert quote.converted_estimated_refund_price is None
    assert quote.converted_amount is None
    assert quote.converted_currency == "CNY"
