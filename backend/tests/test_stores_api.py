from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.store import Store

STORE_IMAGE_URL = "https://cdn.example.test/stores/mcm.jpg"
LEGACY_NEW_YORK_ID = UUID("10000000-0000-0000-0000-000000000002")
LEGACY_AIRPORT_ID = UUID("10000000-0000-0000-0000-000000000003")


def _legacy_store(store_id: UUID, name: str) -> Store:
    return Store(
        id=store_id,
        name=name,
        brand="MCM",
        country="KR",
        city="Seoul",
        type="CITY",
        latitude=37.56,
        longitude=126.98,
        is_active=False,
    )


def test_list_stores_returns_production_stores_with_image_url(
    client: TestClient,
    db_session: Session,
) -> None:
    ferragamo = db_session.get(Store, UUID("10000000-0000-0000-0000-000000000001"))
    assert ferragamo is not None
    ferragamo.image_url = STORE_IMAGE_URL
    db_session.add_all(
        [
            _legacy_store(LEGACY_NEW_YORK_ID, "MCM New York"),
            _legacy_store(LEGACY_AIRPORT_ID, "MCM Airport Store"),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/stores")

    assert response.status_code == 200
    stores = response.json()["stores"]
    assert len(stores) == 8
    assert stores[0]["id"] == "10000000-0000-0000-0000-000000000001"
    assert stores[0]["name"] == "Ferragamo 현대백화점 신촌점"
    assert stores[0]["type"] == "DEPARTMENT_STORE"
    assert stores[0]["airportCode"] is None
    assert stores[0]["address"] == "서울특별시 서대문구 신촌로 83 현대백화점 신촌점 1층"
    assert stores[0]["imageUrl"] == STORE_IMAGE_URL
    assert {store["id"] for store in stores}.isdisjoint(
        {str(LEGACY_NEW_YORK_ID), str(LEGACY_AIRPORT_ID)}
    )

    airport_store = next(store for store in stores if store["name"] == "MCM 현대면세점 인천공항 T1")
    assert airport_store["type"] == "DUTY_FREE"
    assert airport_store["airportCode"] == "ICN"
    assert airport_store["terminal"] == "T1"
    assert airport_store["latitude"] == 37.4602
    assert airport_store["imageUrl"]


def test_nearby_stores_are_sorted_and_exclude_stores_without_coordinates(
    client: TestClient,
    db_session: Session,
) -> None:
    mcm_myeongdong = db_session.get(
        Store,
        UUID("10000000-0000-0000-0000-000000000005"),
    )
    assert mcm_myeongdong is not None
    mcm_myeongdong.image_url = STORE_IMAGE_URL
    db_session.add(_legacy_store(LEGACY_AIRPORT_ID, "MCM Airport Store"))
    db_session.commit()

    response = client.get(
        "/api/v1/stores/nearby",
        params={"latitude": 37.56, "longitude": 126.98, "limit": 2},
    )

    assert response.status_code == 200
    stores = response.json()
    assert len(stores) == 2
    assert stores[0]["name"] == "MCM 롯데면세점 명동본점"
    assert stores[0]["imageUrl"] == STORE_IMAGE_URL
    assert stores[1]["distanceKm"] >= stores[0]["distanceKm"]
    assert all(store["type"] in {"DEPARTMENT_STORE", "DUTY_FREE"} for store in stores)
    assert all(store["latitude"] is not None and store["longitude"] is not None for store in stores)

    all_stores = client.get(
        "/api/v1/stores/nearby",
        params={"latitude": 37.56, "longitude": 126.98},
    ).json()
    assert len(all_stores) == 8
    assert all("imageUrl" in store for store in all_stores)
    assert str(LEGACY_AIRPORT_ID) not in {store["storeId"] for store in all_stores}


def test_nearby_stores_validate_coordinates(client: TestClient) -> None:
    invalid_latitude = client.get(
        "/api/v1/stores/nearby",
        params={"latitude": 91, "longitude": 126.98},
    )
    invalid_longitude = client.get(
        "/api/v1/stores/nearby",
        params={"latitude": 37.56, "longitude": -181},
    )

    assert invalid_latitude.status_code == 422
    assert invalid_longitude.status_code == 422
    assert invalid_latitude.json()["error"]["code"] == "INVALID_REQUEST"
