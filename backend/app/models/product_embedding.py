from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utc_now


class ProductEmbedding(Base):
    __tablename__ = "product_embeddings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    product_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    source_image: Mapped[str] = mapped_column(String(512), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
