from app.models.product import Product
from app.services.pricing import MockPricingService


def test_mock_pricing_matches_contract_example() -> None:
    product = Product(
        product_id="mcm_001",
        sku="SKU001",
        brand="MCM",
        name="Product Name",
        category="bag",
        image_url="https://example.com/product.jpg",
        retail_price_krw=1_090_000,
        tax_refund_supported=True,
    )

    quote = MockPricingService().quote(product, "CNY")

    assert quote.retail_price_krw == 1_090_000
    assert quote.estimated_refund_krw == 60_000
    assert quote.estimated_refund_price_krw == 1_030_000
    assert str(quote.converted_amount) == "5210.35"
    assert quote.converted_currency == "CNY"
    assert quote.instant_refund_eligible is True


def test_mock_pricing_disables_refund_for_unsupported_product() -> None:
    product = Product(
        product_id="mock_unsupported",
        sku="MOCK-UNSUPPORTED",
        brand="Mock",
        name="Unsupported",
        category="other",
        image_url="https://example.com/unsupported.jpg",
        retail_price_krw=100_000,
        tax_refund_supported=False,
    )

    quote = MockPricingService().quote(product, "CNY")

    assert quote.estimated_refund_krw == 0
    assert quote.estimated_refund_price_krw == 100_000
    assert quote.instant_refund_eligible is False
