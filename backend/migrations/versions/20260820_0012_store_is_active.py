"""Add Store active status and deactivate known legacy stores.

Revision ID: 20260820_0012
Revises: 20260820_0011
Create Date: 2026-08-20 00:30:00
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0012"
down_revision: str | Sequence[str] | None = "20260820_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_STORE_IDS = (
    UUID("10000000-0000-0000-0000-000000000002"),
    UUID("10000000-0000-0000-0000-000000000003"),
)


def upgrade() -> None:
    op.add_column(
        "stores",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    stores = sa.table(
        "stores",
        sa.column("id", sa.Uuid()),
        sa.column("is_active", sa.Boolean()),
    )
    op.execute(
        sa.update(stores)
        .where(stores.c.id.in_(LEGACY_STORE_IDS))
        .values(is_active=False)
    )


def downgrade() -> None:
    op.drop_column("stores", "is_active")
