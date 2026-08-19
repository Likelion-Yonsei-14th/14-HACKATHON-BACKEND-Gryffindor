"""Treat receipts as purchases and extend flight details.

Revision ID: 20260819_0008
Revises: 20260819_0007
Create Date: 2026-08-19 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0008"
down_revision: str | Sequence[str] | None = "20260819_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "receipts",
        "store_name",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "flights",
        "departure_airport",
        existing_type=sa.String(length=3),
        nullable=True,
    )
    op.alter_column(
        "flights",
        "arrival_airport",
        existing_type=sa.String(length=3),
        nullable=True,
    )
    op.add_column("flights", sa.Column("terminal", sa.String(length=100), nullable=True))
    op.add_column("flights", sa.Column("arrival_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "flights",
        sa.Column("airport_arrival_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("flights", "airport_arrival_at")
    op.drop_column("flights", "arrival_at")
    op.drop_column("flights", "terminal")
    op.execute(
        sa.text("UPDATE flights SET departure_airport = 'UNK' WHERE departure_airport IS NULL")
    )
    op.execute(sa.text("UPDATE flights SET arrival_airport = 'UNK' WHERE arrival_airport IS NULL"))
    op.alter_column(
        "flights",
        "arrival_airport",
        existing_type=sa.String(length=3),
        nullable=False,
    )
    op.alter_column(
        "flights",
        "departure_airport",
        existing_type=sa.String(length=3),
        nullable=False,
    )
    op.execute(sa.text("UPDATE receipts SET store_name = 'Unknown' WHERE store_name IS NULL"))
    op.alter_column(
        "receipts",
        "store_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )
