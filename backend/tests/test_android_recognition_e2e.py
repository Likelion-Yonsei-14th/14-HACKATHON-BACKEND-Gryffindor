from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.sessions import get_recognition_provider
from app.domain.enums import RecognitionStatus
from app.models.shopping import SessionProduct
from app.providers.mock_recognition import MockRecognitionProvider


def _create_session(client: TestClient) -> str:
    response = client.post("/api/v1/sessions", json={"currency": "CNY"})

    assert response.status_code == 201
    return str(response.json()["sessionId"])


def _android_jpeg_crop() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (480, 320), color=(40, 80, 120)).save(
        buffer,
        format="JPEG",
        quality=85,
    )
    return buffer.getvalue()


def _recognize_from_android(client: TestClient, session_id: str) -> Response:
    return client.post(
        f"/api/v1/sessions/{session_id}/recognize",
        files={"image": ("gen2-crop.jpg", _android_jpeg_crop(), "image/jpeg")},
        data={
            "capturedAt": "2026-08-16T12:34:56.789Z",
            "triggerType": "OCCUPANCY_AND_DWELL",
            "occupancyRatio": "0.24",
            "dwellMs": "1500",
            "trackingId": "gen2-track-42",
        },
    )


def _use_mock_status(test_app: FastAPI, recognition_status: RecognitionStatus) -> None:
    test_app.dependency_overrides[get_recognition_provider] = lambda: MockRecognitionProvider(
        status=recognition_status
    )


def _session_product_count(db_session: Session) -> int:
    row_count = db_session.scalar(select(func.count()).select_from(SessionProduct))
    assert row_count is not None
    return row_count


def test_android_matched_request_and_duplicate_upsert(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
) -> None:
    _use_mock_status(test_app, RecognitionStatus.MATCHED)
    session_id = _create_session(client)

    first_response = _recognize_from_android(client, session_id)

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["recognitionStatus"] == "MATCHED"
    assert first_body["isNew"] is True
    observed_product = first_body["observedProduct"]
    assert observed_product["product"]["productId"] == "test_outer_001"
    assert observed_product["pricing"]
    assert observed_product["observation"] == {
        "triggerType": "OCCUPANCY_AND_DWELL",
        "occupancyRatio": 0.24,
        "dwellMs": 1500,
        "firstObservedAt": "2026-08-16T12:34:56.789000Z",
        "lastObservedAt": "2026-08-16T12:34:56.789000Z",
    }

    duplicate_response = _recognize_from_android(client, session_id)

    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["recognitionStatus"] == "MATCHED"
    assert duplicate_response.json()["isNew"] is False
    assert _session_product_count(db_session) == 1
    session_product = db_session.scalar(select(SessionProduct))
    assert session_product is not None
    assert session_product.observation_count == 2


def test_android_unknown_request_does_not_store_session_product(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
) -> None:
    _use_mock_status(test_app, RecognitionStatus.UNKNOWN)
    session_id = _create_session(client)

    response = _recognize_from_android(client, session_id)

    assert response.status_code == 200
    assert response.json() == {"recognitionStatus": "UNKNOWN"}
    assert _session_product_count(db_session) == 0


def test_android_ambiguous_request_returns_candidates_without_storage(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
) -> None:
    _use_mock_status(test_app, RecognitionStatus.AMBIGUOUS)
    session_id = _create_session(client)

    response = _recognize_from_android(client, session_id)

    assert response.status_code == 200
    assert response.json() == {
        "recognitionStatus": "AMBIGUOUS",
        "candidateProductIds": ["test_outer_001", "test_outer_002"],
    }
    assert _session_product_count(db_session) == 0
