from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class DocumentExtractionModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class ReceiptItemExtraction(DocumentExtractionModel):
    name: str = Field(min_length=1, max_length=255)
    quantity: int | None = Field(gt=0)
    price: int | None = Field(ge=0)


class ReceiptExtraction(DocumentExtractionModel):
    store_name: str | None = Field(min_length=1, max_length=255)
    purchased_at: datetime | None
    currency: str | None = Field(pattern=r"^[A-Z]{3}$")
    total_amount: int | None = Field(ge=0)
    items: list[ReceiptItemExtraction] = Field(min_length=1, max_length=100)

    @field_validator("purchased_at")
    @classmethod
    def require_aware_purchased_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("purchased_at must include a timezone offset")
        return value


class FlightExtraction(DocumentExtractionModel):
    departure_airport: str | None = Field(pattern=r"^[A-Z]{3}$")
    arrival_airport: str | None = Field(pattern=r"^[A-Z]{3}$")
    terminal: str | None = Field(min_length=1, max_length=100)
    flight_number: str | None = Field(min_length=2, max_length=20)
    departure_at: datetime | None
    arrival_at: datetime | None

    @field_validator("departure_at", "arrival_at")
    @classmethod
    def require_aware_flight_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("flight timestamps must include a timezone offset")
        return value

    @model_validator(mode="after")
    def require_distinct_airports(self) -> "FlightExtraction":
        if (
            self.departure_airport is not None
            and self.arrival_airport is not None
            and self.departure_airport == self.arrival_airport
        ):
            raise ValueError("departure and arrival airports must differ")
        return self


class DocumentExtractionProviderError(Exception):
    """A retryable or malformed response from the document provider."""


class DocumentExtractionProvider(Protocol):
    async def extract_receipt(self, image_bytes: bytes) -> ReceiptExtraction: ...

    async def extract_flight(self, image_bytes: bytes) -> FlightExtraction: ...
