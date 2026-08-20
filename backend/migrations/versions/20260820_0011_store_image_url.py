"""Add nullable image URL to stores.

Revision ID: 20260820_0011
Revises: 20260819_0010
Create Date: 2026-08-20 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0011"
down_revision: str | Sequence[str] | None = "20260819_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stores", sa.Column("image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stores", "image_url")
