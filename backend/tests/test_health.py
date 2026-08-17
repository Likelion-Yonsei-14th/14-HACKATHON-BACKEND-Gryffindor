from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app(enable_exchange_rate_startup=False))


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_rejects_unsupported_method() -> None:
    response = client.post("/health")

    assert response.status_code == 405


def test_openapi_exposes_health_endpoint() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
