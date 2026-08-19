from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.me import get_document_extraction_provider, get_recommendation_provider
from app.constants import DEMO_USER_ID
from app.domain.enums import TriggerType
from app.models.personalization import Flight, Receipt, ReceiptItem
from app.models.product import Product
from app.models.shopping import SessionProduct, ShoppingSession
from app.providers.documents import FlightExtraction, ReceiptExtraction
from app.providers.recommendation import (
    RecommendationContext,
    RecommendationDecision,
    RecommendationProductDecision,
    RecommendationStoreDecision,
)
from app.services.recommendations import haversine_distance_km

NEAR_STORE_ID = UUID("10000000-0000-0000-0000-000000000004")
ICN_T2_STORE_ID = UUID("10000000-0000-0000-0000-000000000010")
MISSING_TRIP_ID = "99999999-0000-0000-0000-000000000999"


def _jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeFlightProvider:
    def __init__(self, flight: FlightExtraction) -> None:
        self.flight = flight

    async def extract_receipt(self, image_bytes: bytes) -> ReceiptExtraction:
        del image_bytes
        raise AssertionError("receipt extraction is not expected")

    async def extract_flight(self, image_bytes: bytes) -> FlightExtraction:
        assert image_bytes.startswith(b"\xff\xd8\xff")
        return self.flight


class CapturingRecommendationProvider:
    def __init__(
        self,
        factory: Callable[[RecommendationContext], RecommendationDecision],
    ) -> None:
        self.factory = factory
        self.contexts: list[RecommendationContext] = []

    async def recommend(self, context: RecommendationContext) -> RecommendationDecision:
        self.contexts.append(context)
        return self.factory(context)


def _create_trip(client: TestClient) -> str:
    response = client.post(
        "/api/v1/me/trips",
        json={
            "title": "서울 쇼핑 여행",
            "destinationCity": "Seoul",
            "destinationCountry": "KR",
            "startsAt": "2026-08-20T00:00:00+09:00",
            "endsAt": "2026-08-23T23:59:00+09:00",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_trip_hotel_flight_and_mypage_vertical_slice(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    trip_id = _create_trip(client)
    listed = client.get("/api/v1/me/trips")
    assert listed.status_code == 200
    assert listed.json()["trips"][0]["id"] == trip_id

    patched = client.patch(
        f"/api/v1/me/trips/{trip_id}",
        json={"title": "서울 럭셔리 쇼핑 여행"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "서울 럭셔리 쇼핑 여행"

    hotel = client.put(
        f"/api/v1/me/trips/{trip_id}/hotel",
        json={
            "name": "Hotel Demo Seoul",
            "address": "서울특별시 중구 Demo",
            "latitude": None,
            "longitude": None,
            "checkInAt": "2026-08-20T15:00:00+09:00",
            "checkOutAt": "2026-08-23T11:00:00+09:00",
        },
    )
    assert hotel.status_code == 200
    assert hotel.json()["latitude"] is None
    assert client.get(f"/api/v1/me/trips/{trip_id}/hotel").json()["name"] == (
        "Hotel Demo Seoul"
    )

    provider = FakeFlightProvider(
        FlightExtraction(
            departure_airport="ICN",
            arrival_airport="JFK",
            terminal="T2",
            flight_number="KE081",
            departure_at=datetime.fromisoformat("2026-08-21T10:00:00+09:00"),
            arrival_at=None,
        )
    )
    test_app.dependency_overrides[get_document_extraction_provider] = lambda: provider

    invalid_flight = client.post(
        "/api/v1/me/flights/analyze",
        data={"tripId": MISSING_TRIP_ID},
        files={"image": ("flight.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert invalid_flight.status_code == 404
    assert invalid_flight.json()["error"]["code"] == "TRIP_NOT_FOUND"

    flight = client.post(
        "/api/v1/me/flights/analyze",
        data={"tripId": trip_id},
        files={"image": ("flight.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert flight.status_code == 201
    assert flight.json()["tripId"] == trip_id

    detail = client.get(f"/api/v1/me/trips/{trip_id}")
    assert detail.status_code == 200
    assert detail.json()["trip"]["title"] == "서울 럭셔리 쇼핑 여행"
    assert detail.json()["flights"][0]["flightNumber"] == "KE081"
    assert detail.json()["hotel"]["name"] == "Hotel Demo Seoul"
    assert detail.json()["visitReservations"] == []
    assert client.get("/api/v1/me").json()["trips"][0]["id"] == trip_id

    missing = client.get(f"/api/v1/me/trips/{MISSING_TRIP_ID}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TRIP_NOT_FOUND"


def test_haversine_distance_is_deterministic_and_handles_missing_coordinates() -> None:
    distance = haversine_distance_km(37.56, 126.98, 37.5646, 126.9813)

    assert distance is not None
    assert 0.5 <= distance <= 0.6
    assert haversine_distance_km(None, 126.98, 37.5646, 126.9813) is None


def test_trip_feed_uses_trip_history_location_airport_and_db_allowlist(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
) -> None:
    trip_id = _create_trip(client)
    assert (
        client.put(
            f"/api/v1/me/trips/{trip_id}/hotel",
            json={
                "name": "Hotel Demo Seoul",
                "latitude": 37.56,
                "longitude": 126.98,
            },
        ).status_code
        == 200
    )
    assert client.post("/api/v1/me/wishlist/demo_bag_001").status_code == 200
    assert client.post("/api/v1/me/wishlist/demo_perfume_002").status_code == 200

    products = {product.product_id: product for product in db_session.scalars(select(Product))}
    shopping_session = ShoppingSession(
        user_id=DEMO_USER_ID,
        store_id=NEAR_STORE_ID,
        currency="USD",
    )
    db_session.add(shopping_session)
    db_session.flush()
    db_session.add(
        SessionProduct(
            session_id=shopping_session.id,
            product_id=products["demo_bag_002"].id,
            first_observed_at=datetime(2026, 8, 19, 1, tzinfo=UTC),
            last_observed_at=datetime(2026, 8, 19, 2, tzinfo=UTC),
            max_occupancy_ratio=Decimal("0.4"),
            max_dwell_ms=2500,
            last_trigger_type=TriggerType.OCCUPANCY_AND_DWELL,
            observation_count=4,
        )
    )
    purchase = Receipt(user_id=DEMO_USER_ID, store_name="Demo Store", currency="KRW")
    purchase.items.append(
        ReceiptItem(
            product_name=products["demo_perfume_003"].name,
            product=products["demo_perfume_003"],
            quantity=1,
            price=245_000,
        )
    )
    db_session.add(purchase)
    db_session.add(
        Flight(
            user_id=DEMO_USER_ID,
            trip_id=UUID(trip_id),
            departure_airport="ICN",
            arrival_airport="JFK",
            terminal="T2",
            flight_number="KE081",
        )
    )
    db_session.commit()

    def recommend(context: RecommendationContext) -> RecommendationDecision:
        assert context.trip is not None
        assert str(context.trip.trip_id) == trip_id
        assert context.hotel is not None
        assert context.hotel.name == "Hotel Demo Seoul"
        assert set(context.wishlist_product_ids) >= {"demo_bag_001", "demo_perfume_002"}
        assert any(item.product_id == "demo_bag_002" for item in context.viewed_products)
        assert context.purchased_product_ids == ["demo_perfume_003"]
        assert context.latest_flight is not None
        assert context.latest_flight.terminal == "T2"
        assert len(context.candidate_products) <= 20
        assert len(context.candidate_stores) <= 10
        assert all(
            product.category.casefold() in {"bag", "perfume"}
            for product in context.candidate_products
        )
        assert "demo_perfume_003" not in {
            product.product_id for product in context.candidate_products
        }

        stores = {store.store_id: store for store in context.candidate_stores}
        near_distance = stores[NEAR_STORE_ID].distance_from_hotel_km
        assert near_distance is not None
        assert near_distance < 1
        assert stores[NEAR_STORE_ID].has_wishlist_items is True
        assert stores[ICN_T2_STORE_ID].airport_match is True
        assert stores[ICN_T2_STORE_ID].terminal_match is True
        return RecommendationDecision(
            stores=[
                RecommendationStoreDecision(
                    store_id=NEAR_STORE_ID,
                    reason="숙소에서 가깝고 관심 상품을 취급합니다.",
                    products=[
                        RecommendationProductDecision(
                            product_id="demo_bag_001",
                            reason="관심 있게 본 가방과 잘 맞는 Wishlist 상품입니다.",
                        )
                    ],
                ),
                RecommendationStoreDecision(
                    store_id=ICN_T2_STORE_ID,
                    reason="출국 터미널에서 관심 향수를 준비할 수 있습니다.",
                    products=[
                        RecommendationProductDecision(
                            product_id="demo_perfume_002",
                            reason="Wishlist 향수이며 출국 공항에서 구매할 수 있습니다.",
                        )
                    ],
                ),
            ]
        )

    provider = CapturingRecommendationProvider(recommend)
    test_app.dependency_overrides[get_recommendation_provider] = lambda: provider
    response = client.get(f"/api/v1/me/trips/{trip_id}/feed")

    assert response.status_code == 200
    recommendations = {
        item["product"]["productId"]: item for item in response.json()["recommendations"]
    }
    assert recommendations["demo_bag_001"]["stores"][0]["distanceFromHotelKm"] < 1
    assert recommendations["demo_bag_001"]["stores"][0]["hasWishlistItems"] is True
    assert recommendations["demo_perfume_002"]["stores"][0]["terminal"] == "T2"


def test_trip_feed_rejects_openai_ids_outside_candidates(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    trip_id = _create_trip(client)

    def invalid_decision(context: RecommendationContext) -> RecommendationDecision:
        assert context.hotel is None
        assert all(store.distance_from_hotel_km is None for store in context.candidate_stores)
        return RecommendationDecision(
            stores=[
                RecommendationStoreDecision(
                    store_id=UUID("99999999-0000-0000-0000-000000000999"),
                    reason="invalid",
                    products=[
                        RecommendationProductDecision(
                            product_id=context.candidate_products[0].product_id,
                            reason="invalid",
                        )
                    ],
                )
            ]
        )

    test_app.dependency_overrides[get_recommendation_provider] = lambda: (
        CapturingRecommendationProvider(invalid_decision)
    )
    response = client.get(f"/api/v1/me/trips/{trip_id}/feed")

    assert response.status_code == 200
    assert response.json()["recommendations"] == []


def test_store_wishlist_intersection_and_reservation_validation(
    client: TestClient,
) -> None:
    trip_id = _create_trip(client)
    assert client.post("/api/v1/me/wishlist/demo_bag_001").status_code == 200
    assert client.post("/api/v1/me/wishlist/demo_perfume_002").status_code == 200

    intersection = client.get(f"/api/v1/me/stores/{NEAR_STORE_ID}/wishlist-products")
    assert intersection.status_code == 200
    assert intersection.json() == [{"productId": "demo_bag_001", "name": "Stark Backpack"}]

    valid = client.post(
        f"/api/v1/me/trips/{trip_id}/visit-reservations",
        json={
            "storeId": str(NEAR_STORE_ID),
            "scheduledAt": "2026-08-21T15:00:00+09:00",
            "productIds": ["demo_bag_001"],
        },
    )
    assert valid.status_code == 201
    assert valid.json()["products"][0]["productId"] == "demo_bag_001"
    assert valid.json()["status"] == "RESERVED"

    empty = client.post(
        f"/api/v1/me/trips/{trip_id}/visit-reservations",
        json={
            "storeId": str(NEAR_STORE_ID),
            "scheduledAt": "2026-08-22T15:00:00+09:00",
            "productIds": [],
        },
    )
    assert empty.status_code == 201
    assert empty.json()["products"] == []

    not_carried = client.post(
        f"/api/v1/me/trips/{trip_id}/visit-reservations",
        json={
            "storeId": str(NEAR_STORE_ID),
            "scheduledAt": "2026-08-21T15:00:00+09:00",
            "productIds": ["demo_perfume_002"],
        },
    )
    assert not_carried.status_code == 400
    assert not_carried.json()["error"]["code"] == "INVALID_RESERVATION_PRODUCTS"

    not_wishlisted = client.post(
        f"/api/v1/me/trips/{trip_id}/visit-reservations",
        json={
            "storeId": str(NEAR_STORE_ID),
            "scheduledAt": "2026-08-21T15:00:00+09:00",
            "productIds": ["demo_bag_003"],
        },
    )
    assert not_wishlisted.status_code == 400
    assert not_wishlisted.json()["error"]["code"] == "INVALID_RESERVATION_PRODUCTS"

    reservations = client.get(f"/api/v1/me/trips/{trip_id}/visit-reservations")
    assert reservations.status_code == 200
    assert len(reservations.json()) == 2

    cancelled = client.delete(f"/api/v1/me/visit-reservations/{valid.json()['id']}")
    assert cancelled.status_code == 204
    reservations = client.get(f"/api/v1/me/trips/{trip_id}/visit-reservations")
    statuses = {item["id"]: item["status"] for item in reservations.json()}
    assert statuses[valid.json()["id"]] == "CANCELLED"
