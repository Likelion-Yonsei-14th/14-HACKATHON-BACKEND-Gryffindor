from fastapi.testclient import TestClient


def test_list_stores_returns_demo_stores(client: TestClient) -> None:
    response = client.get("/api/v1/stores")

    assert response.status_code == 200
    assert response.json() == {
        "stores": [
            {
                "id": "10000000-0000-0000-0000-000000000001",
                "name": "MCM Seoul",
                "brand": "MCM",
                "country": "KR",
                "city": "Seoul",
                "type": "CITY",
                "airportCode": None,
            },
            {
                "id": "10000000-0000-0000-0000-000000000002",
                "name": "MCM New York",
                "brand": "MCM",
                "country": "US",
                "city": "New York",
                "type": "CITY",
                "airportCode": None,
            },
            {
                "id": "10000000-0000-0000-0000-000000000003",
                "name": "MCM Airport Store",
                "brand": "MCM",
                "country": "KR",
                "city": "Incheon",
                "type": "AIRPORT",
                "airportCode": "ICN",
            },
        ]
    }
