from fastapi.testclient import TestClient


def test_list_stores_returns_demo_stores(client: TestClient) -> None:
    response = client.get("/api/v1/stores")

    assert response.status_code == 200
    stores = response.json()["stores"]
    assert len(stores) == 10
    assert stores[0]["id"] == "10000000-0000-0000-0000-000000000001"
    assert stores[0]["name"] == "MCM Seoul"
    assert stores[0]["type"] == "CITY"
    assert stores[0]["airportCode"] is None
    assert stores[0]["address"] is None

    t2_store = next(store for store in stores if store["name"] == "ICN Duty Free T2")
    assert t2_store["type"] == "DUTY_FREE"
    assert t2_store["airportCode"] == "ICN"
    assert t2_store["terminal"] == "T2"
    assert t2_store["latitude"] == 37.4687


def test_nearby_stores_are_sorted_and_exclude_stores_without_coordinates(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/stores/nearby",
        params={"latitude": 37.56, "longitude": 126.98, "limit": 2},
    )

    assert response.status_code == 200
    stores = response.json()
    assert len(stores) == 2
    assert stores[0]["name"] == "Seoul Center Department Store B"
    assert stores[1]["distanceKm"] >= stores[0]["distanceKm"]
    assert all(store["type"] in {"DEPARTMENT_STORE", "DUTY_FREE"} for store in stores)
    assert all(store["latitude"] is not None and store["longitude"] is not None for store in stores)

    all_stores = client.get(
        "/api/v1/stores/nearby",
        params={"latitude": 37.56, "longitude": 126.98},
    ).json()
    assert len(all_stores) == 7
    assert all(store["name"] != "MCM Seoul" for store in all_stores)


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
