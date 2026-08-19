from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.me import get_document_extraction_provider, get_recommendation_provider
from app.constants import DEMO_USER_ID
from app.domain.enums import TriggerType
from app.models.personalization import (
    Flight,
    Receipt,
    ReceiptItem,
    StoreProduct,
    User,
    WishlistItem,
)
from app.models.product import Product
from app.models.shopping import SessionProduct, ShoppingSession
from app.providers.documents import (
    DocumentExtractionProviderError,
    FlightExtraction,
    ReceiptExtraction,
    ReceiptItemExtraction,
)
from app.providers.recommendation import (
    RecommendationContext,
    RecommendationDecision,
    RecommendationProductDecision,
    RecommendationProviderError,
    RecommendationStoreDecision,
)


def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeDocumentProvider:
    def __init__(
        self,
        *,
        receipts: list[ReceiptExtraction] | None = None,
        flights: list[FlightExtraction] | None = None,
        error: DocumentExtractionProviderError | None = None,
    ) -> None:
        self.receipts = receipts or []
        self.flights = flights or []
        self.error = error

    async def extract_receipt(self, image_bytes: bytes) -> ReceiptExtraction:
        assert image_bytes.startswith(b"\xff\xd8\xff")
        if self.error is not None:
            raise self.error
        return self.receipts.pop(0)

    async def extract_flight(self, image_bytes: bytes) -> FlightExtraction:
        assert image_bytes.startswith(b"\xff\xd8\xff")
        if self.error is not None:
            raise self.error
        return self.flights.pop(0)


class CapturingRecommendationProvider:
    def __init__(
        self,
        decision_factory: Callable[[RecommendationContext], RecommendationDecision],
    ) -> None:
        self.decision_factory = decision_factory
        self.contexts: list[RecommendationContext] = []

    async def recommend(self, context: RecommendationContext) -> RecommendationDecision:
        self.contexts.append(context)
        return self.decision_factory(context)


class FailingRecommendationProvider:
    async def recommend(self, context: RecommendationContext) -> RecommendationDecision:
        del context
        raise RecommendationProviderError("failed")


def override_document_provider(test_app: FastAPI, provider: FakeDocumentProvider) -> None:
    test_app.dependency_overrides[get_document_extraction_provider] = lambda: provider


def override_recommendation_provider(
    test_app: FastAPI,
    provider: CapturingRecommendationProvider | FailingRecommendationProvider,
) -> None:
    test_app.dependency_overrides[get_recommendation_provider] = lambda: provider


def test_demo_user_and_wishlist_crud_are_android_ready(
    client: TestClient,
    db_session: Session,
) -> None:
    user = db_session.get(User, DEMO_USER_ID)
    assert user is not None
    assert user.name == "Demo User"
    assert client.get("/api/v1/me/wishlist").json() == {"items": []}

    first = client.post("/api/v1/me/wishlist/test_outer_001")
    duplicate = client.post("/api/v1/me/wishlist/test_outer_001")

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert first.json()["productId"] == "test_outer_001"
    assert db_session.scalar(select(func.count()).select_from(WishlistItem)) == 1
    assert client.get("/api/v1/me/wishlist").json()["items"][0]["productId"] == ("test_outer_001")

    missing = client.post("/api/v1/me/wishlist/not_a_product")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PRODUCT_NOT_FOUND"

    assert client.delete("/api/v1/me/wishlist/test_outer_001").status_code == 204
    assert client.delete("/api/v1/me/wishlist/test_outer_001").status_code == 204
    assert client.get("/api/v1/me/wishlist").json() == {"items": []}


def test_receipt_analysis_saves_items_and_only_exact_product_mapping(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
) -> None:
    mapped_product = db_session.scalar(
        select(Product).where(Product.product_id == "test_outer_001")
    )
    assert mapped_product is not None
    provider = FakeDocumentProvider(
        receipts=[
            ReceiptExtraction(
                store_name="Demo Department Store",
                purchased_at=datetime.fromisoformat("2026-08-19T14:30:00+09:00"),
                currency="KRW",
                total_amount=169_000,
                items=[
                    ReceiptItemExtraction(
                        name=f"  {mapped_product.name.upper()}  ",
                        quantity=1,
                        price=159_000,
                    ),
                    ReceiptItemExtraction(
                        name="Unmapped Receipt Product",
                        quantity=1,
                        price=10_000,
                    ),
                ],
            )
        ]
    )
    override_document_provider(test_app, provider)

    response = client.post(
        "/api/v1/me/receipts/analyze",
        files={"image": ("receipt.jpg", jpeg_bytes(), "image/jpeg")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["storeName"] == "Demo Department Store"
    assert payload["purchasedAt"] == "2026-08-19T05:30:00Z"
    assert {item["productId"] for item in payload["items"]} == {"test_outer_001", None}
    assert db_session.scalar(select(func.count()).select_from(Receipt)) == 1
    assert db_session.scalar(select(func.count()).select_from(ReceiptItem)) == 2

    purchases = client.get("/api/v1/me/purchases")
    assert purchases.status_code == 200
    assert len(purchases.json()) == 1
    purchase_items = purchases.json()[0]["items"]
    matched = next(item for item in purchase_items if item["product"] is not None)
    unmatched = next(item for item in purchase_items if item["product"] is None)
    assert matched["product"]["productId"] == "test_outer_001"
    assert matched["fallbackProductName"] is None
    assert unmatched["fallbackProductName"] == "Unmapped Receipt Product"

    my_page = client.get("/api/v1/me").json()
    assert "receipts" not in my_page
    assert len(my_page["purchasedProducts"]) == 2
    assert any(
        item["fallbackProductName"] == "Unmapped Receipt Product"
        for item in my_page["purchasedProducts"]
    )


def test_receipt_provider_failure_is_503_and_does_not_save(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
) -> None:
    override_document_provider(
        test_app,
        FakeDocumentProvider(error=DocumentExtractionProviderError("invalid output")),
    )

    response = client.post(
        "/api/v1/me/receipts/analyze",
        files={"image": ("receipt.jpg", jpeg_bytes(), "image/jpeg")},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DOCUMENT_EXTRACTION_PROVIDER_ERROR"
    assert db_session.scalar(select(func.count()).select_from(Receipt)) == 0


def test_purchase_capture_keeps_unmatched_item_when_store_is_unreadable(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    override_document_provider(
        test_app,
        FakeDocumentProvider(
            receipts=[
                ReceiptExtraction(
                    store_name=None,
                    purchased_at=None,
                    currency=None,
                    total_amount=None,
                    items=[
                        ReceiptItemExtraction(
                            name="준지_남성",
                            quantity=None,
                            price=None,
                        )
                    ],
                )
            ]
        ),
    )

    analyzed = client.post(
        "/api/v1/me/receipts/analyze",
        files={"image": ("receipt.jpg", jpeg_bytes(), "image/jpeg")},
    )
    purchases = client.get("/api/v1/me/purchases")

    assert analyzed.status_code == 201
    assert analyzed.json()["storeName"] is None
    assert purchases.status_code == 200
    assert purchases.json()[0]["storeName"] is None
    assert purchases.json()[0]["items"][0]["product"] is None
    assert purchases.json()[0]["items"][0]["fallbackProductName"] == "준지_남성"


def test_receipt_rejects_invalid_image(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    override_document_provider(test_app, FakeDocumentProvider())

    response = client.post(
        "/api/v1/me/receipts/analyze",
        files={"image": ("receipt.jpg", b"not-an-image", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IMAGE"


def test_flight_analysis_and_my_page_use_latest_flight(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    provider = FakeDocumentProvider(
        flights=[
            FlightExtraction(
                departure_airport="ICN",
                arrival_airport="LAX",
                terminal="T2",
                flight_number="KE017",
                departure_at=datetime.fromisoformat("2026-08-20T10:00:00+09:00"),
                arrival_at=datetime.fromisoformat("2026-08-20T05:00:00-07:00"),
            ),
            FlightExtraction(
                departure_airport="ICN",
                arrival_airport="JFK",
                terminal="T2",
                flight_number="KE081",
                departure_at=datetime.fromisoformat("2026-08-21T10:00:00+09:00"),
                arrival_at=datetime.fromisoformat("2026-08-21T11:00:00-04:00"),
            ),
        ]
    )
    override_document_provider(test_app, provider)

    first = client.post(
        "/api/v1/me/flights/analyze",
        files={"image": ("flight-1.jpg", jpeg_bytes(), "image/jpeg")},
    )
    second = client.post(
        "/api/v1/me/flights/analyze",
        files={"image": ("flight-2.jpg", jpeg_bytes(), "image/jpeg")},
    )
    my_page = client.get("/api/v1/me")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["departureAt"] == "2026-08-21T01:00:00Z"
    assert second.json()["arrivalAt"] == "2026-08-21T15:00:00Z"
    assert second.json()["airportArrivalAt"] is None
    assert my_page.status_code == 200
    assert my_page.json()["flight"]["flightNumber"] == "KE081"
    assert my_page.json()["user"] == {"id": 1, "name": "Demo User"}


def test_flight_analysis_allows_missing_fields_and_manual_patch(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    provider = FakeDocumentProvider(
        flights=[
            FlightExtraction(
                departure_airport=None,
                arrival_airport=None,
                terminal=None,
                flight_number=None,
                departure_at=None,
                arrival_at=None,
            )
        ]
    )
    override_document_provider(test_app, provider)

    analyzed = client.post(
        "/api/v1/me/flights/analyze",
        files={"image": ("flight.jpg", jpeg_bytes(), "image/jpeg")},
    )

    assert analyzed.status_code == 201
    assert analyzed.json()["departureAirport"] is None
    assert analyzed.json()["arrivalAt"] is None
    assert analyzed.json()["airportArrivalAt"] is None

    flight_id = analyzed.json()["id"]
    updated = client.patch(
        f"/api/v1/me/flights/{flight_id}",
        json={
            "departureAirport": "ICN",
            "arrivalAirport": "KUL",
            "terminal": "T2",
            "flightNumber": "SQ607",
            "departureAt": "2026-08-21T10:00:00+09:00",
            "arrivalAt": "2026-08-21T13:30:00+08:00",
            "airportArrivalAt": "2026-08-21T07:00:00+09:00",
        },
    )

    assert updated.status_code == 200
    assert updated.json()["terminal"] == "T2"
    assert updated.json()["departureAt"] == "2026-08-21T01:00:00Z"
    assert updated.json()["arrivalAt"] == "2026-08-21T05:30:00Z"
    assert updated.json()["airportArrivalAt"] == "2026-08-20T22:00:00Z"

    missing = client.patch(
        "/api/v1/me/flights/99999999-0000-0000-0000-000000000999",
        json={"terminal": "T1"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "FLIGHT_NOT_FOUND"


def _seed_recommendation_history(db: Session) -> None:
    products = {product.product_id: product for product in db.scalars(select(Product)).all()}
    store_id = UUID("10000000-0000-0000-0000-000000000001")
    shopping_session = ShoppingSession(
        user_id=DEMO_USER_ID,
        store_id=store_id,
        currency="USD",
    )
    db.add(shopping_session)
    db.flush()
    db.add(
        SessionProduct(
            session_id=shopping_session.id,
            product_id=products["demo_perfume_001"].id,
            first_observed_at=datetime(2026, 8, 19, 1, tzinfo=UTC),
            last_observed_at=datetime(2026, 8, 19, 2, tzinfo=UTC),
            max_occupancy_ratio=Decimal("0.4"),
            max_dwell_ms=2400,
            last_trigger_type=TriggerType.OCCUPANCY_AND_DWELL,
            observation_count=3,
        )
    )
    db.add(
        WishlistItem(
            user_id=DEMO_USER_ID,
            product_id=products["test_outer_001"].id,
        )
    )
    receipt = Receipt(
        user_id=DEMO_USER_ID,
        store_name="Demo Store",
        total_amount=25_000,
        currency="KRW",
    )
    receipt.items.append(
        ReceiptItem(
            product_name=products["demo_mouse_001"].name,
            product=products["demo_mouse_001"],
            quantity=1,
            price=25_000,
        )
    )
    receipt.items.append(
        ReceiptItem(
            product_name="준지_남성",
            product=None,
            quantity=1,
            price=621_000,
        )
    )
    db.add(receipt)
    db.add(
        Flight(
            user_id=DEMO_USER_ID,
            departure_airport="ICN",
            arrival_airport="JFK",
            flight_number="KE081",
            departure_at=datetime(2026, 8, 21, 1, tzinfo=UTC),
        )
    )
    db.commit()


def test_recommendation_context_contains_all_history_and_only_db_candidates(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
) -> None:
    _seed_recommendation_history(db_session)
    airport_store_id = UUID("10000000-0000-0000-0000-000000000003")

    def valid_decision(context: RecommendationContext) -> RecommendationDecision:
        assert context.candidate_stores[0].store_id == airport_store_id
        return RecommendationDecision(
            stores=[
                RecommendationStoreDecision(
                    store_id=airport_store_id,
                    reason="출국 전에 방문하기 편리합니다.",
                    products=[
                        RecommendationProductDecision(
                            product_id="demo_perfume_001",
                            reason="스마트글래스로 여러 번 본 상품입니다.",
                        )
                    ],
                )
            ]
        )

    provider = CapturingRecommendationProvider(valid_decision)
    override_recommendation_provider(test_app, provider)

    response = client.get("/api/v1/me/recommendations")

    assert response.status_code == 200
    context = provider.contexts[0]
    assert context.wishlist_product_ids == ["test_outer_001"]
    assert context.viewed_products[0].product_id == "demo_perfume_001"
    assert context.viewed_products[0].observation_count == 3
    assert context.purchased_product_ids == ["demo_mouse_001"]
    matched_purchase = next(
        item for item in context.purchased_products if item.product_id == "demo_mouse_001"
    )
    unmatched_purchase = next(
        item for item in context.purchased_products if item.product_id is None
    )
    assert matched_purchase.name is not None
    assert matched_purchase.brand is not None
    assert unmatched_purchase.fallback_product_name == "준지_남성"
    assert unmatched_purchase.store_name == "Demo Store"
    assert context.latest_flight is not None
    assert context.latest_flight.arrival_airport == "JFK"
    candidate_ids = {product.product_id for product in context.candidate_products}
    assert "demo_mouse_001" not in candidate_ids
    assert all(set(store.product_ids) <= candidate_ids for store in context.candidate_stores)
    assert response.json()["stores"][0]["storeId"] == str(airport_store_id)
    assert response.json()["stores"][0]["products"][0]["product"]["productId"] == (
        "demo_perfume_001"
    )


@pytest.mark.parametrize("invalid_kind", ["store", "product", "relationship"])
def test_recommendation_allowlist_removes_invalid_results(
    invalid_kind: str,
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store_id = UUID("10000000-0000-0000-0000-000000000001")
    product = db_session.scalar(select(Product).where(Product.product_id == "demo_perfume_001"))
    assert product is not None
    if invalid_kind == "relationship":
        relation = db_session.get(StoreProduct, (store_id, product.id))
        assert relation is not None
        db_session.delete(relation)
        db_session.commit()

    returned_store_id = (
        UUID("99999999-0000-0000-0000-000000000999") if invalid_kind == "store" else store_id
    )
    returned_product_id = "missing_product" if invalid_kind == "product" else product.product_id
    provider = CapturingRecommendationProvider(
        lambda context: RecommendationDecision(
            stores=[
                RecommendationStoreDecision(
                    store_id=returned_store_id,
                    reason="invalid test",
                    products=[
                        RecommendationProductDecision(
                            product_id=returned_product_id,
                            reason="invalid test",
                        )
                    ],
                )
            ]
        )
    )
    override_recommendation_provider(test_app, provider)

    with caplog.at_level("WARNING"):
        response = client.get("/api/v1/me/recommendations")

    assert response.status_code == 200
    assert response.json() == {"stores": []}
    assert "recommendation_validation_failed" in caplog.text


def test_recommendation_tolerates_missing_personalization_data(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    def first_candidate(context: RecommendationContext) -> RecommendationDecision:
        store = context.candidate_stores[0]
        return RecommendationDecision(
            stores=[
                RecommendationStoreDecision(
                    store_id=store.store_id,
                    reason="DB 후보 매장입니다.",
                    products=[
                        RecommendationProductDecision(
                            product_id=store.product_ids[0],
                            reason="DB 후보 상품입니다.",
                        )
                    ],
                )
            ]
        )

    provider = CapturingRecommendationProvider(first_candidate)
    override_recommendation_provider(test_app, provider)

    response = client.get("/api/v1/me/recommendations")

    assert response.status_code == 200
    assert response.json()["stores"]
    context = provider.contexts[0]
    assert context.wishlist_product_ids == []
    assert context.viewed_products == []
    assert context.purchased_product_ids == []
    assert context.purchased_products == []
    assert context.latest_flight is None


def test_recommendation_provider_failure_is_503(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    override_recommendation_provider(test_app, FailingRecommendationProvider())

    response = client.get("/api/v1/me/recommendations")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RECOMMENDATION_PROVIDER_ERROR"


def test_b5_api_e2e_flow_with_fake_openai_providers(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
) -> None:
    receipt_product = db_session.scalar(
        select(Product).where(Product.product_id == "test_outer_002")
    )
    assert receipt_product is not None
    document_provider = FakeDocumentProvider(
        receipts=[
            ReceiptExtraction(
                store_name="E2E Demo Store",
                purchased_at=datetime.fromisoformat("2026-08-19T14:30:00+09:00"),
                currency="KRW",
                total_amount=receipt_product.retail_price_krw,
                items=[
                    ReceiptItemExtraction(
                        name=receipt_product.name,
                        quantity=1,
                        price=receipt_product.retail_price_krw,
                    )
                ],
            )
        ],
        flights=[
            FlightExtraction(
                departure_airport="ICN",
                arrival_airport="JFK",
                terminal=None,
                flight_number="KE081",
                departure_at=datetime.fromisoformat("2026-08-21T10:00:00+09:00"),
                arrival_at=None,
            )
        ],
    )
    override_document_provider(test_app, document_provider)

    def recommend_first_allowlisted(context: RecommendationContext) -> RecommendationDecision:
        store = context.candidate_stores[0]
        return RecommendationDecision(
            stores=[
                RecommendationStoreDecision(
                    store_id=store.store_id,
                    reason="E2E allowlisted store",
                    products=[
                        RecommendationProductDecision(
                            product_id=store.product_ids[0],
                            reason="E2E allowlisted product",
                        )
                    ],
                )
            ]
        )

    recommendation_provider = CapturingRecommendationProvider(recommend_first_allowlisted)
    override_recommendation_provider(test_app, recommendation_provider)

    assert db_session.get(User, DEMO_USER_ID) is not None
    stores_response = client.get("/api/v1/stores")
    assert stores_response.status_code == 200
    store_id = stores_response.json()["stores"][0]["id"]
    session_response = client.post(
        "/api/v1/sessions",
        json={"currency": "USD", "storeId": store_id},
    )
    assert session_response.status_code == 201
    assert session_response.json()["storeId"] == store_id

    assert client.post("/api/v1/me/wishlist/test_outer_001").status_code == 200
    assert client.get("/api/v1/me/wishlist").json()["items"][0]["productId"] == ("test_outer_001")
    assert (
        client.post(
            "/api/v1/me/receipts/analyze",
            files={"image": ("receipt.jpg", jpeg_bytes(), "image/jpeg")},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/me/flights/analyze",
            files={"image": ("flight.jpg", jpeg_bytes(), "image/jpeg")},
        ).status_code
        == 201
    )

    recommendation_response = client.get("/api/v1/me/recommendations")
    assert recommendation_response.status_code == 200
    recommended_store = recommendation_response.json()["stores"][0]
    recommended_product_id = recommended_store["products"][0]["product"]["productId"]
    recommended_product = db_session.scalar(
        select(Product).where(Product.product_id == recommended_product_id)
    )
    assert recommended_product is not None
    assert (
        db_session.get(
            StoreProduct,
            (UUID(recommended_store["storeId"]), recommended_product.id),
        )
        is not None
    )

    my_page_response = client.get("/api/v1/me")
    assert my_page_response.status_code == 200
    assert my_page_response.json()["wishlist"][0]["productId"] == "test_outer_001"
    assert my_page_response.json()["purchasedProducts"][0]["product"]["productId"] == (
        "test_outer_002"
    )
    assert my_page_response.json()["flight"]["flightNumber"] == "KE081"
    assert client.delete("/api/v1/me/wishlist/test_outer_001").status_code == 204
