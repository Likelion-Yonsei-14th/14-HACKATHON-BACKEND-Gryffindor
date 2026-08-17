from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.sessions import get_recognition_provider
from app.core.config import Settings, get_settings
from app.domain.enums import RecognitionStatus
from app.models.shopping import SessionProduct
from app.providers.mock_recognition import MockRecognitionProvider
from app.providers.recognition import (
    RecognitionCandidate,
    RecognitionDecision,
    RecognitionProviderError,
)


class StaticRecognitionProvider:
    def __init__(
        self,
        decision: RecognitionDecision | None = None,
        error: RecognitionProviderError | None = None,
    ) -> None:
        self._decision = decision
        self._error = error
        self.candidates: list[RecognitionCandidate] = []

    async def recognize(
        self,
        image_bytes: bytes,
        candidates: list[RecognitionCandidate],
    ) -> RecognitionDecision:
        del image_bytes
        self.candidates = candidates
        if self._error is not None:
            raise self._error
        if self._decision is None:
            raise AssertionError("Static provider requires a decision")
        return self._decision


class DebugImageCheckingProvider:
    def __init__(self, directory: Path, expected_image_bytes: bytes) -> None:
        self._directory = directory
        self._expected_image_bytes = expected_image_bytes
        self.saved_image_path: Path | None = None

    async def recognize(
        self,
        image_bytes: bytes,
        candidates: list[RecognitionCandidate],
    ) -> RecognitionDecision:
        del candidates
        saved_images = list(self._directory.iterdir())
        assert len(saved_images) == 1
        self.saved_image_path = saved_images[0]
        assert self.saved_image_path.read_bytes() == self._expected_image_bytes
        assert image_bytes == self._expected_image_bytes
        return RecognitionDecision(status=RecognitionStatus.UNKNOWN)


def create_session(client: TestClient) -> str:
    response = client.post("/api/v1/sessions", json={"currency": "CNY"})
    assert response.status_code == 201
    return str(response.json()["sessionId"])


def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="JPEG")
    return buffer.getvalue()


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def recognize(
    client: TestClient,
    session_id: str,
    *,
    captured_at: datetime,
    occupancy_ratio: float = 0.24,
    dwell_ms: int = 1500,
    image_bytes: bytes | None = None,
) -> Response:
    return client.post(
        f"/api/v1/sessions/{session_id}/recognize",
        files={
            "image": (
                "crop.jpg",
                image_bytes if image_bytes is not None else jpeg_bytes(),
                "image/jpeg",
            )
        },
        data={
            "capturedAt": captured_at.isoformat().replace("+00:00", "Z"),
            "triggerType": "OCCUPANCY_AND_DWELL",
            "occupancyRatio": str(occupancy_ratio),
            "dwellMs": str(dwell_ms),
            "trackingId": "track-1",
        },
    )


def test_recognition_debug_image_saving_is_off_by_default(
    client: TestClient,
    test_app: FastAPI,
    tmp_path: Path,
) -> None:
    debug_directory = tmp_path / "recognition_crops"
    test_app.dependency_overrides[get_settings] = lambda: Settings(
        recognition_debug_image_dir=debug_directory
    )
    test_app.dependency_overrides[get_recognition_provider] = lambda: StaticRecognitionProvider(
        decision=RecognitionDecision(status=RecognitionStatus.UNKNOWN)
    )
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )

    assert response.status_code == 200
    assert response.json() == {"recognitionStatus": "UNKNOWN"}
    assert not debug_directory.exists()


def test_recognition_debug_image_is_saved_before_provider_call(
    client: TestClient,
    test_app: FastAPI,
    tmp_path: Path,
) -> None:
    captured_at = datetime(2026, 8, 15, 13, 35, 1, 123456, tzinfo=UTC)
    debug_directory = tmp_path / "recognition_crops"
    original_image_bytes = jpeg_bytes()
    provider = DebugImageCheckingProvider(debug_directory, original_image_bytes)
    test_app.dependency_overrides[get_settings] = lambda: Settings(
        recognition_debug_save_images=True,
        recognition_debug_image_dir=debug_directory,
    )
    test_app.dependency_overrides[get_recognition_provider] = lambda: provider
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=captured_at,
        image_bytes=original_image_bytes,
    )

    assert response.status_code == 200
    assert response.json() == {"recognitionStatus": "UNKNOWN"}
    assert provider.saved_image_path is not None
    assert "20260815T133501_123456Z" in provider.saved_image_path.name
    assert session_id in provider.saved_image_path.name
    assert provider.saved_image_path.suffix == ".jpg"


def test_create_session_matches_contract(client: TestClient) -> None:
    response = client.post("/api/v1/sessions", json={"currency": "CNY"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"sessionId", "status", "currency", "startedAt"}
    UUID(body["sessionId"])
    assert body["status"] == "ACTIVE"
    assert body["currency"] == "CNY"
    assert datetime.fromisoformat(body["startedAt"].replace("Z", "+00:00")).tzinfo is not None


def test_mock_vertical_slice_and_duplicate_upsert(
    client: TestClient,
    db_session: Session,
) -> None:
    session_id = create_session(client)
    first_captured_at = datetime(2026, 8, 15, 13, 35, tzinfo=UTC)
    second_captured_at = first_captured_at + timedelta(seconds=3)

    first_response = recognize(client, session_id, captured_at=first_captured_at)

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["recognitionStatus"] == "MATCHED"
    assert first_body["isNew"] is True
    assert set(first_body) == {"recognitionStatus", "isNew", "observedProduct"}
    observed = first_body["observedProduct"]
    assert observed["product"] == {
        "productId": "test_outer_001",
        "sku": "MUSINSA-5477019",
        "brand": "HAVE HAD",
        "name": "워시드 포켓 유틸리티 자켓 (데님 블루)",
        "category": "jacket",
        "imageUrl": "https://example.com/products/test_outer_001.jpg",
    }
    assert observed["pricing"] == {
        "retailPriceKrw": 159_000,
        "estimatedRefundKrw": 0,
        "estimatedRefundPriceKrw": 159_000,
        "convertedAmount": "804.32",
        "convertedCurrency": "CNY",
        "instantRefundEligible": False,
        "pricingMode": "MOCK",
    }

    second_response = recognize(
        client,
        session_id,
        captured_at=second_captured_at,
        occupancy_ratio=0.4,
        dwell_ms=2000,
    )

    assert second_response.status_code == 200
    assert second_response.json()["isNew"] is False
    observation = second_response.json()["observedProduct"]["observation"]
    assert observation["occupancyRatio"] == 0.4
    assert observation["dwellMs"] == 2000
    assert observation["lastObservedAt"] == "2026-08-15T13:35:03Z"

    row_count = db_session.scalar(select(func.count()).select_from(SessionProduct))
    session_product = db_session.scalar(select(SessionProduct))
    assert row_count == 1
    assert session_product is not None
    assert session_product.observation_count == 2
    assert session_product.max_occupancy_ratio == Decimal("0.4")
    assert session_product.max_dwell_ms == 2000
    assert session_product.last_observed_at.replace(tzinfo=UTC) == second_captured_at

    list_response = client.get(f"/api/v1/sessions/{session_id}/products")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["sessionId"] == session_id
    assert len(list_body["items"]) == 1
    assert list_body["items"][0]["product"]["productId"] == "test_outer_001"
    assert list_body["items"][0]["purchaseState"] == "UNSET"
    assert list_body["items"][0]["interested"] is False


@pytest.mark.parametrize(
    ("recognition_status", "expected_body"),
    [
        (
            RecognitionStatus.AMBIGUOUS,
            {
                "recognitionStatus": "AMBIGUOUS",
                "candidateProductIds": ["demo_lotion_001", "demo_mouse_001"],
            },
        ),
        (RecognitionStatus.UNKNOWN, {"recognitionStatus": "UNKNOWN"}),
    ],
)
def test_non_match_results_are_not_stored(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
    recognition_status: RecognitionStatus,
    expected_body: dict[str, object],
) -> None:
    test_app.dependency_overrides[get_recognition_provider] = lambda: MockRecognitionProvider(
        status=recognition_status
    )
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )

    assert response.status_code == 200
    assert response.json() == expected_body
    assert db_session.scalar(select(func.count()).select_from(SessionProduct)) == 0


def test_complete_session_then_reject_recognition(client: TestClient) -> None:
    session_id = create_session(client)

    complete_response = client.post(f"/api/v1/sessions/{session_id}/complete")

    assert complete_response.status_code == 200
    complete_body = complete_response.json()
    assert set(complete_body) == {"sessionId", "status", "completedAt"}
    assert complete_body["sessionId"] == session_id
    assert complete_body["status"] == "COMPLETED"

    recognition_response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )
    assert recognition_response.status_code == 409
    assert recognition_response.json() == {
        "error": {
            "code": "SESSION_NOT_ACTIVE",
            "message": "Recognition is allowed only for an active shopping session.",
        }
    }


def test_invalid_image_is_rejected(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(
        f"/api/v1/sessions/{session_id}/recognize",
        files={"image": ("crop.jpg", b"not-an-image", "image/jpeg")},
        data={
            "capturedAt": "2026-08-15T13:35:00Z",
            "triggerType": "DWELL",
            "occupancyRatio": "0.2",
            "dwellMs": "1500",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_IMAGE",
            "message": "A valid JPEG or PNG image is required.",
        }
    }


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("crop.jpg", "image/jpeg", jpeg_bytes()),
        ("crop.png", "image/png", png_bytes()),
    ],
)
def test_recognition_accepts_supported_image_formats(
    client: TestClient,
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    session_id = create_session(client)

    response = client.post(
        f"/api/v1/sessions/{session_id}/recognize",
        files={"image": (filename, content, content_type)},
        data={
            "capturedAt": "2026-08-16T12:00:00Z",
            "triggerType": "OCCUPANCY_AND_DWELL",
            "occupancyRatio": "0.24",
            "dwellMs": "1500",
            "trackingId": "android-track-1",
        },
    )

    assert response.status_code == 200
    assert response.json()["recognitionStatus"] == "MATCHED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("occupancyRatio", "-0.01"),
        ("occupancyRatio", "1.01"),
        ("dwellMs", "-1"),
        ("triggerType", "CENTER"),
        ("capturedAt", "not-an-iso-8601-timestamp"),
    ],
)
def test_invalid_recognition_metadata_uses_error_contract(
    client: TestClient,
    field: str,
    value: str,
) -> None:
    session_id = create_session(client)
    data = {
        "capturedAt": "2026-08-16T12:00:00Z",
        "triggerType": "OCCUPANCY_AND_DWELL",
        "occupancyRatio": "0.24",
        "dwellMs": "1500",
    }
    data[field] = value

    response = client.post(
        f"/api/v1/sessions/{session_id}/recognize",
        files={"image": ("crop.jpg", jpeg_bytes(), "image/jpeg")},
        data=data,
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "INVALID_REQUEST",
            "message": "The request payload is invalid.",
        }
    }


def test_provider_failure_is_mapped_to_contract_error(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    test_app.dependency_overrides[get_recognition_provider] = lambda: MockRecognitionProvider(
        should_fail=True
    )
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RECOGNITION_PROVIDER_ERROR"


def test_common_provider_error_is_mapped_to_contract_error(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    test_app.dependency_overrides[get_recognition_provider] = lambda: StaticRecognitionProvider(
        error=RecognitionProviderError("timeout")
    )
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "RECOGNITION_PROVIDER_ERROR",
            "message": "The recognition provider is temporarily unavailable.",
        }
    }


@pytest.mark.parametrize(
    "decision",
    [
        RecognitionDecision(
            status=RecognitionStatus.MATCHED,
            product_id="invented_product_id",
        ),
        RecognitionDecision(
            status=RecognitionStatus.AMBIGUOUS,
            candidate_product_ids=("test_outer_001", "invented_product_id"),
        ),
    ],
)
def test_provider_ids_outside_catalog_allowlist_become_unknown(
    client: TestClient,
    test_app: FastAPI,
    db_session: Session,
    decision: RecognitionDecision,
) -> None:
    test_app.dependency_overrides[get_recognition_provider] = lambda: StaticRecognitionProvider(
        decision=decision
    )
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )

    assert response.status_code == 200
    assert response.json() == {"recognitionStatus": "UNKNOWN"}
    assert db_session.scalar(select(func.count()).select_from(SessionProduct)) == 0


def test_real_provider_shape_uses_same_matched_api_dto(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    test_app.dependency_overrides[get_recognition_provider] = lambda: StaticRecognitionProvider(
        decision=RecognitionDecision(
            status=RecognitionStatus.MATCHED,
            product_id="test_outer_002",
        )
    )
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"recognitionStatus", "isNew", "observedProduct"}
    assert body["recognitionStatus"] == "MATCHED"
    assert body["observedProduct"]["product"]["productId"] == "test_outer_002"


def test_a4_demo_products_are_the_three_candidate_allowlist_with_reference_images(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    provider = StaticRecognitionProvider(
        decision=RecognitionDecision(status=RecognitionStatus.UNKNOWN)
    )
    test_app.dependency_overrides[get_recognition_provider] = lambda: provider
    test_app.dependency_overrides[get_settings] = lambda: Settings(recognition_max_candidates=3)
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )

    assert response.status_code == 200
    assert [candidate.product_id for candidate in provider.candidates] == [
        "demo_lotion_001",
        "demo_mouse_001",
        "demo_perfume_001",
    ]
    assert [candidate.reference_image_url for candidate in provider.candidates] == [
        "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/"
        "0000/0022/A00000022655337ko.jpg?l=ko",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/"
        "Logitech_M185_mouse_HS05.jpg/960px-Logitech_M185_mouse_HS05.jpg",
        "https://img.kingpowerclick.com/cdn-cgi/image/format=auto/kingpower-com/image/"
        "upload/w_640/v1753241145/prod/1008697-L1.jpg",
    ]


def test_valid_ambiguous_ids_are_filtered_and_deduplicated(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    test_app.dependency_overrides[get_recognition_provider] = lambda: StaticRecognitionProvider(
        decision=RecognitionDecision(
            status=RecognitionStatus.AMBIGUOUS,
            candidate_product_ids=(
                "test_outer_001",
                "invented_product_id",
                "test_outer_001",
                "test_outer_002",
            ),
        )
    )
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )

    assert response.status_code == 200
    assert response.json() == {
        "recognitionStatus": "AMBIGUOUS",
        "candidateProductIds": ["test_outer_001", "test_outer_002"],
    }


def test_openai_mode_without_api_key_uses_provider_error_contract(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    test_app.dependency_overrides[get_settings] = lambda: Settings(
        recognition_provider="openai",
        openai_api_key=None,
    )
    session_id = create_session(client)

    response = recognize(
        client,
        session_id,
        captured_at=datetime(2026, 8, 15, 13, 35, tzinfo=UTC),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RECOGNITION_PROVIDER_ERROR"


def test_missing_session_returns_contract_error(client: TestClient) -> None:
    response = client.get(f"/api/v1/sessions/{uuid4()}/products")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_openapi_exposes_b1_contract(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    paths = document["paths"]
    assert "/api/v1/sessions" in paths
    assert "/api/v1/sessions/{sessionId}/complete" in paths
    assert "/api/v1/sessions/{sessionId}/recognize" in paths
    assert "/api/v1/sessions/{sessionId}/products" in paths
    recognize_operation = paths["/api/v1/sessions/{sessionId}/recognize"]["post"]
    assert "multipart/form-data" in recognize_operation["requestBody"]["content"]
    assert recognize_operation["parameters"][0]["name"] == "sessionId"

    multipart_schema_ref = recognize_operation["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]["$ref"]
    multipart_schema_name = multipart_schema_ref.rsplit("/", maxsplit=1)[-1]
    multipart_schema = document["components"]["schemas"][multipart_schema_name]
    assert set(multipart_schema["properties"]) == {
        "image",
        "capturedAt",
        "triggerType",
        "occupancyRatio",
        "dwellMs",
        "trackingId",
    }
    assert set(multipart_schema["required"]) == {
        "image",
        "capturedAt",
        "triggerType",
        "occupancyRatio",
        "dwellMs",
    }

    recognition_schema = document["components"]["schemas"]["RecognitionResponse"]
    assert set(recognition_schema["properties"]) == {
        "recognitionStatus",
        "isNew",
        "observedProduct",
        "candidateProductIds",
    }
