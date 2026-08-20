"""Normalize the fixed user name for single-user mode.

Revision ID: 20260821_0013
Revises: 20260820_0012
Create Date: 2026-08-21 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0013"
down_revision: str | Sequence[str] | None = "20260820_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String(length=120)),
    )
    op.execute(sa.update(users).where(users.c.id == 1).values(name="Single User"))


def downgrade() -> None:
    # The preceding revision now uses the same normalized name.
    pass
