from datetime import UTC, datetime
from io import BytesIO
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.me import get_document_extraction_provider
from app.constants import DEMO_USER_ID
from app.domain.enums import RefundMethod
from app.models.personalization import Flight, Receipt, ReceiptItem
from app.models.product import Product
from app.providers.documents import FlightExtraction, ReceiptExtraction, ReceiptItemExtraction
from app.services.refund_checklist import RefundChecklistService

MISSING_ID = "99999999-0000-0000-0000-000000000999"


def _jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeReceiptProvider:
    def __init__(self, receipt: ReceiptExtraction) -> None:
        self.receipt = receipt

    async def extract_receipt(self, image_bytes: bytes) -> ReceiptExtraction:
        assert image_bytes.startswith(b"\xff\xd8\xff")
        return self.receipt

    async def extract_flight(self, image_bytes: bytes) -> FlightExtraction:
        del image_bytes
        raise AssertionError("flight extraction is not expected")


def _create_trip(client: TestClient) -> UUID:
    response = client.post("/api/v1/me/trips", json={"title": "환급 테스트 여행"})
    assert response.status_code == 201
    return UUID(response.json()["id"])


def _product(db: Session, product_id: str) -> Product:
    product = db.scalar(select(Product).where(Product.product_id == product_id))
    assert product is not None
    return product


def _add_purchase(
    db: Session,
    trip_id: UUID,
    *,
    refund_method: RefundMethod,
    product_id: str = "demo_mouse_001",
    total_amount: int | None = 25_000,
    currency: str | None = "KRW",
    purchased_at: datetime | None = None,
) -> Receipt:
    product = _product(db, product_id)
    purchase = Receipt(
        user_id=DEMO_USER_ID,
        trip_id=trip_id,
        refund_method=refund_method,
        store_name="Demo Store",
        purchased_at=purchased_at,
        total_amount=total_amount,
        currency=currency,
    )
    purchase.items.append(
        ReceiptItem(
            product_name=product.name,
            product=product,
            quantity=1,
            price=total_amount,
        )
    )
    db.add(purchase)
    db.commit()
    return purchase


def _checklist(client: TestClient, trip_id: UUID) -> dict[str, Any]:
    response = client.get(f"/api/v1/me/trips/{trip_id}/refund-checklist")
    assert response.status_code == 200
    return response.json()


def _item_ids(payload: dict[str, Any]) -> list[str]:
    items = cast(list[dict[str, Any]], payload["items"])
    return [item["id"] for item in items]


def test_no_refund_supported_purchase_returns_empty_items(
    client: TestClient,
    db_session: Session,
) -> None:
    trip_id = _create_trip(client)
    _add_purchase(
        db_session,
        trip_id,
        refund_method=RefundMethod.UNKNOWN,
        product_id="test_outer_001",
    )
    fallback_purchase = Receipt(
        user_id=DEMO_USER_ID,
        trip_id=trip_id,
        refund_method=RefundMethod.UNKNOWN,
        store_name="Fallback Store",
        total_amount=30_000,
        currency="KRW",
    )
    fallback_purchase.items.append(
        ReceiptItem(
            product_name="OCR fallback only",
            product=None,
            quantity=1,
            price=30_000,
        )
    )
    db_session.add(fallback_purchase)
    db_session.commit()

    payload = _checklist(client, trip_id)

    assert payload["status"] == "NO_ELIGIBLE_PURCHASES"
    assert payload["items"] == []


def test_immediate_only_has_no_refund_receipt_step(
    client: TestClient,
    db_session: Session,
) -> None:
    trip_id = _create_trip(client)
    _add_purchase(db_session, trip_id, refund_method=RefundMethod.IMMEDIATE)

    payload = _checklist(client, trip_id)

    assert payload["status"] == "IMMEDIATE_REFUND_ONLY"
    assert payload["items"] == []
    assert "즉시환급" in str(payload["notice"])


def test_airport_purchase_has_four_short_steps(
    client: TestClient,
    db_session: Session,
) -> None:
    trip_id = _create_trip(client)
    _add_purchase(db_session, trip_id, refund_method=RefundMethod.AIRPORT)

    payload = _checklist(client, trip_id)

    assert payload["status"] == "ACTION_REQUIRED"
    assert _item_ids(payload) == [
        "prepare-refund-documents",
        "prepare-purchased-goods",
        "customs-export-confirmation",
        "receive-refund",
    ]
    assert len(payload["items"]) <= 4


def test_downtown_purchase_requires_customs_but_not_another_refund(
    client: TestClient,
    db_session: Session,
) -> None:
    trip_id = _create_trip(client)
    _add_purchase(db_session, trip_id, refund_method=RefundMethod.DOWNTOWN)

    item_ids = _item_ids(_checklist(client, trip_id))

    assert "customs-export-confirmation" in item_ids
    assert "receive-refund" not in item_ids


def test_airport_and_downtown_use_a_duplicate_free_union(
    client: TestClient,
    db_session: Session,
) -> None:
    trip_id = _create_trip(client)
    _add_purchase(db_session, trip_id, refund_method=RefundMethod.AIRPORT)
    _add_purchase(db_session, trip_id, refund_method=RefundMethod.DOWNTOWN)

    item_ids = _item_ids(_checklist(client, trip_id))

    assert len(item_ids) == 4
    assert len(item_ids) == len(set(item_ids))


@pytest.mark.parametrize(
    ("transaction_total", "expected"),
    [(999_999, True), (1_000_000, False)],
)
def test_immediate_refund_transaction_boundary(
    transaction_total: int,
    expected: bool,
) -> None:
    assert (
        RefundChecklistService.is_potentially_immediate_refund_eligible(
            transaction_total,
            5_000_000,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("known_total", "expected"),
    [(5_000_000, True), (5_000_001, False)],
)
def test_immediate_refund_known_cumulative_boundary(
    known_total: int,
    expected: bool,
) -> None:
    assert (
        RefundChecklistService.is_potentially_immediate_refund_eligible(
            999_999,
            known_total,
        )
        is expected
    )


def test_potential_eligibility_uses_purchase_total_without_changing_method(
    client: TestClient,
    db_session: Session,
) -> None:
    trip_id = _create_trip(client)
    below = _add_purchase(
        db_session,
        trip_id,
        refund_method=RefundMethod.UNKNOWN,
        total_amount=999_999,
    )
    at_limit = _add_purchase(
        db_session,
        trip_id,
        refund_method=RefundMethod.UNKNOWN,
        total_amount=1_000_000,
    )
    below.items[0].price = 1_000_000
    at_limit.items[0].price = 999_999
    db_session.commit()

    result = RefundChecklistService(db_session).build(trip_id)

    assert result.potential_immediate_eligibility[below.id] is True
    assert result.potential_immediate_eligibility[at_limit.id] is False
    assert below.refund_method == RefundMethod.UNKNOWN
    assert at_limit.refund_method == RefundMethod.UNKNOWN


def test_departure_after_three_calendar_months_adds_one_warning(
    client: TestClient,
    db_session: Session,
) -> None:
    trip_id = _create_trip(client)
    _add_purchase(
        db_session,
        trip_id,
        refund_method=RefundMethod.AIRPORT,
        purchased_at=datetime(2026, 1, 31, 10, tzinfo=UTC),
    )
    db_session.add(
        Flight(
            user_id=DEMO_USER_ID,
            trip_id=trip_id,
            departure_at=datetime(2026, 5, 1, 10, tzinfo=UTC),
        )
    )
    db_session.commit()

    item_ids = _item_ids(_checklist(client, trip_id))

    assert item_ids.count("export-deadline-warning") == 1
    assert len(item_ids) == 5


def test_missing_purchase_and_departure_dates_do_not_add_warning_or_crash(
    client: TestClient,
    db_session: Session,
) -> None:
    trip_id = _create_trip(client)
    _add_purchase(
        db_session,
        trip_id,
        refund_method=RefundMethod.UNKNOWN,
        purchased_at=None,
    )
    db_session.add(Flight(user_id=DEMO_USER_ID, trip_id=trip_id, departure_at=None))
    db_session.commit()

    payload = _checklist(client, trip_id)

    assert payload["status"] == "ACTION_REQUIRED"
    assert "export-deadline-warning" not in _item_ids(payload)


def test_receipt_analyze_optional_trip_and_purchase_refund_method_patch(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    trip_id = _create_trip(client)
    provider = FakeReceiptProvider(
        ReceiptExtraction(
            store_name="Demo Store",
            purchased_at=datetime(2026, 8, 19, tzinfo=UTC),
            currency="KRW",
            total_amount=25_000,
            items=[
                ReceiptItemExtraction(
                    name="Demo Mouse",
                    quantity=1,
                    price=25_000,
                )
            ],
        )
    )
    test_app.dependency_overrides[get_document_extraction_provider] = lambda: provider

    invalid_trip = client.post(
        "/api/v1/me/receipts/analyze",
        data={"tripId": MISSING_ID},
        files={"image": ("receipt.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert invalid_trip.status_code == 404
    assert invalid_trip.json()["error"]["code"] == "TRIP_NOT_FOUND"

    analyzed = client.post(
        "/api/v1/me/receipts/analyze",
        data={"tripId": str(trip_id)},
        files={"image": ("receipt.jpg", _jpeg_bytes(), "image/jpeg")},
    )

    assert analyzed.status_code == 201
    assert analyzed.json()["tripId"] == str(trip_id)
    assert analyzed.json()["refundMethod"] == "UNKNOWN"

    purchase_id = analyzed.json()["id"]
    patched = client.patch(
        f"/api/v1/me/purchases/{purchase_id}",
        json={"refundMethod": "AIRPORT"},
    )
    assert patched.status_code == 200
    assert patched.json()["refundMethod"] == "AIRPORT"

    missing = client.patch(
        f"/api/v1/me/purchases/{MISSING_ID}",
        json={"refundMethod": "IMMEDIATE"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PURCHASE_NOT_FOUND"


def test_missing_trip_checklist_is_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/me/trips/{MISSING_ID}/refund-checklist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TRIP_NOT_FOUND"
