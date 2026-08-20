"""Tests for PUT /api/v1/sessions/{sessionId}/review endpoint.

Covers:
1. Review endpoint normal save
2. Session-absent productId rejection
3. interested → wishlist addition
4. PURCHASED → GET /me purchasedProducts
5. Receipt vs Session purchase deduplication
6. Mutual exclusivity (purchased wins over interested)
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import SINGLE_USER_ID
from app.domain.enums import PurchaseState, TriggerType
from app.models.personalization import Receipt, ReceiptItem, WishlistItem
from app.models.product import Product
from app.models.shopping import SessionProduct, ShoppingSession
from app.models.store import Store


def _seed_multi_product_session(db_session: Session) -> tuple[str, list[str]]:
    """Create a session with multiple products directly in DB for review testing."""
    store = db_session.scalar(select(Store).where(Store.is_active.is_(True)).limit(1))
    assert store is not None

    products = list(db_session.scalars(select(Product).limit(3)).all())
    assert len(products) >= 3

    shopping_session = ShoppingSession(
        user_id=SINGLE_USER_ID,
        store_id=store.id,
        currency="USD",
    )
    db_session.add(shopping_session)
    db_session.flush()

    product_ids: list[str] = []
    for product in products:
        sp = SessionProduct(
            session_id=shopping_session.id,
            product_id=product.id,
            first_observed_at=datetime(2026, 8, 19, 10, tzinfo=UTC),
            last_observed_at=datetime(2026, 8, 19, 10, 5, tzinfo=UTC),
            max_occupancy_ratio=Decimal("0.3"),
            max_dwell_ms=2000,
            last_trigger_type=TriggerType.OCCUPANCY_AND_DWELL,
            observation_count=2,
        )
        db_session.add(sp)
        product_ids.append(product.product_id)

    db_session.commit()
    return str(shopping_session.id), product_ids


def test_review_saves_purchase_and_interest_states(
    client: TestClient,
    db_session: Session,
) -> None:
    session_id, product_ids = _seed_multi_product_session(db_session)

    response = client.put(
        f"/api/v1/sessions/{session_id}/review",
        json={
            "purchasedProductIds": [product_ids[0]],
            "interestedProductIds": [product_ids[1]],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert product_ids[0] in body["purchasedProductIds"]
    assert product_ids[1] in body["interestedProductIds"]
    assert product_ids[2] not in body["purchasedProductIds"]
    assert product_ids[2] not in body["interestedProductIds"]

    # Verify DB state
    session_products = list(
        db_session.scalars(
            select(SessionProduct).where(SessionProduct.session_id == UUID(session_id))
        ).all()
    )
    sp_map = {sp.product.product_id: sp for sp in session_products}
    assert sp_map[product_ids[0]].purchase_state == PurchaseState.PURCHASED
    assert sp_map[product_ids[0]].interested is False
    assert sp_map[product_ids[1]].purchase_state == PurchaseState.UNSET
    assert sp_map[product_ids[1]].interested is True
    assert sp_map[product_ids[2]].purchase_state == PurchaseState.UNSET
    assert sp_map[product_ids[2]].interested is False


def test_review_rejects_product_not_in_session(
    client: TestClient,
    db_session: Session,
) -> None:
    session_id, _ = _seed_multi_product_session(db_session)

    response = client.put(
        f"/api/v1/sessions/{session_id}/review",
        json={
            "purchasedProductIds": ["nonexistent_product_xyz"],
            "interestedProductIds": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PRODUCT_IDS"


def test_review_rejects_missing_session(client: TestClient) -> None:
    response = client.put(
        f"/api/v1/sessions/{uuid4()}/review",
        json={
            "purchasedProductIds": [],
            "interestedProductIds": [],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_review_interested_adds_to_wishlist(
    client: TestClient,
    db_session: Session,
) -> None:
    session_id, product_ids = _seed_multi_product_session(db_session)

    # Ensure wishlist is empty initially
    wishlist_response = client.get("/api/v1/me/wishlist")
    assert wishlist_response.json()["items"] == []

    # Submit review with interested product
    response = client.put(
        f"/api/v1/sessions/{session_id}/review",
        json={
            "purchasedProductIds": [],
            "interestedProductIds": [product_ids[1]],
        },
    )
    assert response.status_code == 200

    # Verify wishlist
    wishlist_response = client.get("/api/v1/me/wishlist")
    wishlist_ids = [item["productId"] for item in wishlist_response.json()["items"]]
    assert product_ids[1] in wishlist_ids


def test_review_interested_wishlist_is_idempotent(
    client: TestClient,
    db_session: Session,
) -> None:
    session_id, product_ids = _seed_multi_product_session(db_session)

    # Add to wishlist manually first
    client.post(f"/api/v1/me/wishlist/{product_ids[1]}")

    # Submit review with the same product as interested
    response = client.put(
        f"/api/v1/sessions/{session_id}/review",
        json={
            "purchasedProductIds": [],
            "interestedProductIds": [product_ids[1]],
        },
    )
    assert response.status_code == 200

    # Verify no duplicate in wishlist
    from sqlalchemy import func

    count = db_session.scalar(select(func.count()).select_from(WishlistItem))
    assert count == 1


def test_review_purchased_appears_in_my_page(
    client: TestClient,
    db_session: Session,
) -> None:
    session_id, product_ids = _seed_multi_product_session(db_session)

    # Submit review with first product as purchased
    response = client.put(
        f"/api/v1/sessions/{session_id}/review",
        json={
            "purchasedProductIds": [product_ids[0]],
            "interestedProductIds": [],
        },
    )
    assert response.status_code == 200

    # Verify MyPage
    my_page = client.get("/api/v1/me")
    assert my_page.status_code == 200
    purchased_products = my_page.json()["purchasedProducts"]
    purchased_product_ids = [
        item["product"]["productId"] for item in purchased_products if item["product"] is not None
    ]
    assert product_ids[0] in purchased_product_ids


def test_review_purchased_dedup_with_receipt(
    client: TestClient,
    db_session: Session,
) -> None:
    """If a product is both in receipt and session PURCHASED, only receipt entry shows."""
    session_id, product_ids = _seed_multi_product_session(db_session)

    # Create a receipt with product_ids[0]
    product = db_session.scalar(select(Product).where(Product.product_id == product_ids[0]))
    assert product is not None
    receipt = Receipt(
        user_id=SINGLE_USER_ID,
        store_name="Test Store",
        purchased_at=datetime(2026, 8, 19, tzinfo=UTC),
        total_amount=product.retail_price_krw,
        currency="KRW",
    )
    receipt.items.append(
        ReceiptItem(
            product_name=product.name,
            product=product,
            quantity=2,
            price=product.retail_price_krw,
        )
    )
    db_session.add(receipt)
    db_session.commit()

    # Also mark as purchased in session review
    response = client.put(
        f"/api/v1/sessions/{session_id}/review",
        json={
            "purchasedProductIds": [product_ids[0]],
            "interestedProductIds": [],
        },
    )
    assert response.status_code == 200

    # Verify MyPage has only one entry for product_ids[0]
    my_page = client.get("/api/v1/me")
    assert my_page.status_code == 200
    purchased_products = my_page.json()["purchasedProducts"]
    matching = [
        item
        for item in purchased_products
        if item["product"] is not None and item["product"]["productId"] == product_ids[0]
    ]
    # Should be exactly 1 (from receipt, quantity=2)
    assert len(matching) == 1
    assert matching[0]["quantity"] == 2  # Receipt version (not session version with qty=1)


def test_review_mutual_exclusivity_purchased_wins(
    client: TestClient,
    db_session: Session,
) -> None:
    """If a product is in both purchased and interested, purchased wins."""
    session_id, product_ids = _seed_multi_product_session(db_session)

    response = client.put(
        f"/api/v1/sessions/{session_id}/review",
        json={
            "purchasedProductIds": [product_ids[0]],
            "interestedProductIds": [product_ids[0]],  # same product
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert product_ids[0] in body["purchasedProductIds"]
    assert product_ids[0] not in body["interestedProductIds"]


def test_review_with_scripted_recognition_flow(
    client: TestClient,
    db_session: Session,
) -> None:
    """E2E: seed a session product directly → complete session → review."""
    session_id, product_ids = _seed_multi_product_session(db_session)

    # Complete session
    client.post(f"/api/v1/sessions/{session_id}/complete")

    # Submit review - purchase first, interest second
    response = client.put(
        f"/api/v1/sessions/{session_id}/review",
        json={
            "purchasedProductIds": [product_ids[0]],
            "interestedProductIds": [product_ids[1]],
        },
    )

    assert response.status_code == 200
    assert product_ids[0] in response.json()["purchasedProductIds"]
    assert product_ids[1] in response.json()["interestedProductIds"]

    # Verify in MyPage
    my_page = client.get("/api/v1/me")
    assert my_page.status_code == 200
    purchased_ids = [
        item["product"]["productId"]
        for item in my_page.json()["purchasedProducts"]
        if item["product"] is not None
    ]
    assert product_ids[0] in purchased_ids

    # Verify wishlist
    wishlist = client.get("/api/v1/me/wishlist")
    wishlist_ids = [item["productId"] for item in wishlist.json()["items"]]
    assert product_ids[1] in wishlist_ids
