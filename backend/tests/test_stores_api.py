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
