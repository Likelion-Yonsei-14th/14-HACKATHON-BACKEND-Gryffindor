import logging
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.sessions import get_recognition_provider
from app.domain.enums import RecognitionStatus
from app.models.shopping import SessionProduct
from app.providers.scripted_recognition import ScriptedRecognitionProvider


def _create_session(client: TestClient) -> str:
    stores_response = client.get("/api/v1/stores")
    assert stores_response.status_code == 200
    store_id = stores_response.json()["stores"][0]["id"]
    response = client.post(
        "/api/v1/sessions",
        json={"currency": "CNY", "storeId": store_id},
    )

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


def _recognize_from_android(
    client: TestClient,
    session_id: str,
    *,
    request_id: str | None = None,
) -> Response:
    headers = {"X-Request-ID": request_id} if request_id is not None else None
    return client.post(
        f"/api/v1/sessions/{session_id}/recognize",
        headers=headers,
        files={"image": ("gen2-crop.jpg", _android_jpeg_crop(), "image/jpeg")},
        data={
            "capturedAt": "2026-08-16T12:34:56.789Z",
            "triggerType": "OCCUPANCY_AND_DWELL",
            "occupancyRatio": "0.24",
            "dwellMs": "1500",
            "trackingId": "gen2-track-42",
        },
    )


def _use_scripted_status(test_app: FastAPI, recognition_status: RecognitionStatus) -> None:
    test_app.dependency_overrides[get_recognition_provider] = lambda: ScriptedRecognitionProvider(
        status=recognition_status,
        product_id="diptyque_leau_papier_100_001",
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
    _use_scripted_status(test_app, RecognitionStatus.MATCHED)
    session_id = _create_session(client)

    first_response = _recognize_from_android(client, session_id)

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["recognitionStatus"] == "MATCHED"
    assert first_body["isNew"] is True
    observed_product = first_body["observedProduct"]
    assert observed_product["product"]["productId"] == "diptyque_leau_papier_100_001"
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


def test_android_request_has_correlated_recognition_log(
    client: TestClient,
    test_app: FastAPI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _use_scripted_status(test_app, RecognitionStatus.MATCHED)
    session_id = _create_session(client)
    request_id = "android-e2e-request-001"

    with caplog.at_level(logging.INFO, logger="app.api.sessions"):
        response = _recognize_from_android(client, session_id, request_id=request_id)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    recognition_logs = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("recognition_completed ")
    ]
    assert len(recognition_logs) == 1
    message = recognition_logs[0]
    expected_fields = [
        f"request_id={request_id}",
        f"session_id={session_id}",
        f"image_bytes={len(_android_jpeg_crop())}",
        "provider=ScriptedRecognitionProvider",
        "trigger_type=OCCUPANCY_AND_DWELL",
        "occupancy_ratio=0.2400",
        "dwell_ms=1500",
        "recognition_status=MATCHED",
        "product_id=diptyque_leau_papier_100_001",
        "recognition_latency_ms=",
        "total_latency_ms=",
    ]
    assert all(field in message for field in expected_fields)


def test_android_unknown_request_does_not_store_session_product(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
) -> None:
    _use_scripted_status(test_app, RecognitionStatus.UNKNOWN)
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
    _use_scripted_status(test_app, RecognitionStatus.AMBIGUOUS)
    session_id = _create_session(client)

    response = _recognize_from_android(client, session_id)

    assert response.status_code == 200
    assert response.json() == {
        "recognitionStatus": "AMBIGUOUS",
        "candidateProductIds": [
            "anillo_fragrance_of_life_10_001",
            "dashu_aqua_dive_50_001",
        ],
    }
    assert _session_product_count(db_session) == 0
