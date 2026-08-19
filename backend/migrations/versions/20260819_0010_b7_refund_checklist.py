"""Add purchase trip link and refund method for B7 checklist.

Revision ID: 20260819_0010
Revises: 20260819_0009
Create Date: 2026-08-19 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0010"
down_revision: str | Sequence[str] | None = "20260819_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("trip_id", sa.Uuid(), nullable=True))
    op.add_column(
        "receipts",
        sa.Column(
            "refund_method",
            sa.String(length=16),
            server_default="UNKNOWN",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_receipts_trip_id_trips",
        "receipts",
        "trips",
        ["trip_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_receipts_trip_id"), "receipts", ["trip_id"], unique=False)
    op.create_check_constraint(
        "ck_receipts_refund_method",
        "receipts",
        "refund_method IN ('UNKNOWN', 'IMMEDIATE', 'DOWNTOWN', 'AIRPORT')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_receipts_refund_method", "receipts", type_="check")
    op.drop_index(op.f("ix_receipts_trip_id"), table_name="receipts")
    op.drop_constraint("fk_receipts_trip_id_trips", "receipts", type_="foreignkey")
    op.drop_column("receipts", "refund_method")
    op.drop_column("receipts", "trip_id")
