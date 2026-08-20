from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.constants import SINGLE_USER_ID
from app.domain.enums import RefundChecklistStatus, RefundMethod
from app.errors import AppError
from app.models.personalization import Receipt
from app.repositories.personalization import PersonalizationRepository
from app.repositories.trips import TripRepository


@dataclass(frozen=True, slots=True)
class RefundChecklistItem:
    id: str
    title: str
    description: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class RefundChecklistResult:
    trip_id: UUID
    status: RefundChecklistStatus
    items: tuple[RefundChecklistItem, ...]
    potential_immediate_eligibility: dict[UUID, bool | None]
    notice: str | None = None


# Fixed MVP rules based on 외국인관광객 등에 대한 부가가치세 및 개별소비세 특례규정
# [시행 2026. 1. 2.] [대통령령 제35947호]. These strings and decisions are deterministic.
# 제8조: prepare the purchase receipt and sales-confirmation information when needed.
_PREPARE_DOCUMENTS = RefundChecklistItem(
    id="prepare-refund-documents",
    title="환급 서류를 준비하세요",
    description="구매 영수증과 환급 관련 판매확인서를 준비하세요.",
)
# 제9조: keep goods available for a possible customs export confirmation at departure.
_PREPARE_GOODS = RefundChecklistItem(
    id="prepare-purchased-goods",
    title="구매 물품을 준비하세요",
    description="출국 시 세관의 확인 요청에 대비해 구매 물품을 확인할 수 있도록 준비하세요.",
)
_CUSTOMS_CONFIRMATION = RefundChecklistItem(
    id="customs-export-confirmation",
    title="세관 반출 확인을 진행하세요",
    description="출국 시 필요한 경우 세관의 반출 확인을 받으세요.",
)
# 제9조: AIRPORT/UNKNOWN may still require a refund step after export confirmation.
_RECEIVE_REFUND = RefundChecklistItem(
    id="receive-refund",
    title="환급을 받으세요",
    description="반출 확인 후 이용 가능한 환급창구 또는 환급 절차를 이용하세요.",
)
_EXPORT_DEADLINE_WARNING = RefundChecklistItem(
    id="export-deadline-warning",
    title="환급 가능 기간을 확인하세요",
    description="일부 구매가 구매일로부터 3개월을 초과해 출국 예정입니다.",
)
_IMMEDIATE_REFUND_NOTICE = (
    "즉시환급이 적용된 구매입니다. 출국 시 세관의 확인 요청이 있을 수 있으므로 "
    "구매 물품과 영수증을 보관하세요."
)


class RefundChecklistService:
    # 제6조제2항: one transaction is strictly below KRW 1,000,000, and the known
    # cumulative immediate-refund transaction total is at most KRW 5,000,000.
    INSTANT_TRANSACTION_LIMIT_KRW = 1_000_000
    INSTANT_CUMULATIVE_LIMIT_KRW = 5_000_000
    EXPORT_DEADLINE_MONTHS = 3

    def __init__(self, db: Session) -> None:
        self._personalization = PersonalizationRepository(db)
        self._trips = TripRepository(db)

    def build(self, trip_id: UUID) -> RefundChecklistResult:
        if self._trips.get(SINGLE_USER_ID, trip_id) is None:
            raise AppError(404, "TRIP_NOT_FOUND", "Trip was not found.")

        purchases = self._personalization.list_trip_receipts(SINGLE_USER_ID, trip_id)
        session_purchases = self._personalization.list_session_purchased_products(SINGLE_USER_ID)
        potential_eligibility = self._potential_immediate_eligibility(purchases)

        if not purchases and not session_purchases:
            return RefundChecklistResult(
                trip_id=trip_id,
                status=RefundChecklistStatus.NO_ELIGIBLE_PURCHASES,
                items=(),
                potential_immediate_eligibility=potential_eligibility,
            )

        latest_flight = self._personalization.latest_trip_flight(SINGLE_USER_ID, trip_id)
        departure_at = latest_flight.departure_at if latest_flight is not None else None
        has_deadline_warning = any(
            _exceeds_export_deadline(purchase.purchased_at, departure_at) for purchase in purchases
        )

        methods = {purchase.refund_method for purchase in purchases}
        if session_purchases:
            # Review purchases have no receipt/refund-method relation in the current schema.
            # Treat them as an active-trip purchase whose refund method is not yet known.
            methods.add(RefundMethod.UNKNOWN)
        if methods == {RefundMethod.IMMEDIATE}:
            items = [_EXPORT_DEADLINE_WARNING] if has_deadline_warning else []
            return RefundChecklistResult(
                trip_id=trip_id,
                status=RefundChecklistStatus.IMMEDIATE_REFUND_ONLY,
                items=tuple(items),
                notice=_IMMEDIATE_REFUND_NOTICE,
                potential_immediate_eligibility=potential_eligibility,
            )

        items = [_PREPARE_DOCUMENTS, _PREPARE_GOODS, _CUSTOMS_CONFIRMATION]
        # 제10조의4: DOWNTOWN is already refunded but still depends on export confirmation.
        if RefundMethod.AIRPORT in methods or RefundMethod.UNKNOWN in methods:
            items.append(_RECEIVE_REFUND)
        if has_deadline_warning:
            items.append(_EXPORT_DEADLINE_WARNING)

        return RefundChecklistResult(
            trip_id=trip_id,
            status=RefundChecklistStatus.ACTION_REQUIRED,
            items=tuple(items),
            potential_immediate_eligibility=potential_eligibility,
        )

    @classmethod
    def is_potentially_immediate_refund_eligible(
        cls,
        transaction_total: int,
        known_instant_refund_total: int,
    ) -> bool:
        """Return a potential amount-rule result, never an actual refund-method decision."""
        return (
            transaction_total < cls.INSTANT_TRANSACTION_LIMIT_KRW
            and known_instant_refund_total <= cls.INSTANT_CUMULATIVE_LIMIT_KRW
        )

    def _potential_immediate_eligibility(
        self,
        purchases: list[Receipt],
    ) -> dict[UUID, bool | None]:
        known_immediate_total = sum(
            purchase.total_amount
            for purchase in purchases
            if purchase.refund_method == RefundMethod.IMMEDIATE
            and _known_krw_total(purchase) is not None
            and purchase.total_amount is not None
        )
        results: dict[UUID, bool | None] = {}
        for purchase in purchases:
            transaction_total = _known_krw_total(purchase)
            if transaction_total is None:
                results[purchase.id] = None
                continue
            projected_total = known_immediate_total
            if purchase.refund_method != RefundMethod.IMMEDIATE:
                projected_total += transaction_total
            results[purchase.id] = self.is_potentially_immediate_refund_eligible(
                transaction_total,
                projected_total,
            )
        return results


def _known_krw_total(purchase: Receipt) -> int | None:
    if purchase.total_amount is None or purchase.currency is None:
        return None
    if purchase.currency.upper() != "KRW":
        return None
    return purchase.total_amount


def _exceeds_export_deadline(
    purchased_at: datetime | None,
    departure_at: datetime | None,
) -> bool:
    # 제6조제1항제1호: export must occur within three calendar months of purchase.
    if purchased_at is None or departure_at is None:
        return False
    purchase_utc = _as_utc(purchased_at)
    departure_utc = _as_utc(departure_at)
    return departure_utc > _add_months(purchase_utc, RefundChecklistService.EXPORT_DEADLINE_MONTHS)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
