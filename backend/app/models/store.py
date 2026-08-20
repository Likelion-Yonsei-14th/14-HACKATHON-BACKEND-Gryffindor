from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Float, String, Text, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.personalization import StoreProduct
    from app.models.shopping import ShoppingSession
    from app.models.trip import VisitReservation


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str] = mapped_column(String(120), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    airport_code: Mapped[str | None] = mapped_column(String(3))
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    terminal: Mapped[str | None] = mapped_column(String(100))
    opening_hours: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    shopping_sessions: Mapped[list[ShoppingSession]] = relationship(back_populates="store")
    store_products: Mapped[list[StoreProduct]] = relationship(
        back_populates="store",
        cascade="all, delete-orphan",
    )
    visit_reservations: Mapped[list[VisitReservation]] = relationship(back_populates="store")
