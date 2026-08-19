from enum import StrEnum


class SessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class RecognitionStatus(StrEnum):
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class TriggerType(StrEnum):
    OCCUPANCY = "OCCUPANCY"
    DWELL = "DWELL"
    OCCUPANCY_AND_DWELL = "OCCUPANCY_AND_DWELL"


class PurchaseState(StrEnum):
    UNSET = "UNSET"
    PURCHASED = "PURCHASED"


class ReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    CANCELLED = "CANCELLED"


class RefundMethod(StrEnum):
    UNKNOWN = "UNKNOWN"
    IMMEDIATE = "IMMEDIATE"
    DOWNTOWN = "DOWNTOWN"
    AIRPORT = "AIRPORT"


class RefundChecklistStatus(StrEnum):
    NO_ELIGIBLE_PURCHASES = "NO_ELIGIBLE_PURCHASES"
    IMMEDIATE_REFUND_ONLY = "IMMEDIATE_REFUND_ONLY"
    ACTION_REQUIRED = "ACTION_REQUIRED"
