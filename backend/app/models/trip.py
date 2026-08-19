from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.enums import ReservationStatus
from app.models.common import utc_now

if TYPE_CHECKING:
    from app.models.personalization import Flight, Receipt, User
    from app.models.product import Product
    from app.models.store import Store


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    destination_city: Mapped[str | None] = mapped_column(String(120))
    destination_country: Mapped[str | None] = mapped_column(String(2))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="trips")
    flights: Mapped[list[Flight]] = relationship(back_populates="trip")
    receipts: Mapped[list[Receipt]] = relationship(back_populates="trip")
    hotel: Mapped[HotelStay | None] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        uselist=False,
    )
    visit_reservations: Mapped[list[VisitReservation]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
    )


class HotelStay(Base):
    __tablename__ = "hotel_stays"
    __table_args__ = (
        UniqueConstraint("trip_id", name="uq_hotel_stays_trip_id"),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_hotel_stays_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_hotel_stays_longitude_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    trip_id: Mapped[UUID] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    trip: Mapped[Trip] = relationship(back_populates="hotel")


class VisitReservation(Base):
    __tablename__ = "visit_reservations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RESERVED', 'CANCELLED')",
            name="reservation_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trip_id: Mapped[UUID] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(
            ReservationStatus,
            name="reservation_status",
            native_enum=False,
            length=16,
            create_constraint=False,
        ),
        nullable=False,
        default=ReservationStatus.RESERVED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    trip: Mapped[Trip] = relationship(back_populates="visit_reservations")
    store: Mapped[Store] = relationship(back_populates="visit_reservations")
    reservation_products: Mapped[list[VisitReservationProduct]] = relationship(
        back_populates="reservation",
        cascade="all, delete-orphan",
        order_by="VisitReservationProduct.product_id",
    )


class VisitReservationProduct(Base):
    __tablename__ = "visit_reservation_products"

    reservation_id: Mapped[UUID] = mapped_column(
        ForeignKey("visit_reservations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        primary_key=True,
    )

    reservation: Mapped[VisitReservation] = relationship(back_populates="reservation_products")
    product: Mapped[Product] = relationship(back_populates="visit_reservation_products")
