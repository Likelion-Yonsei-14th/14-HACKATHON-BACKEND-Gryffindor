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
