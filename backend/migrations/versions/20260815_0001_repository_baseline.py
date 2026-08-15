"""Create the repository baseline.

Revision ID: 20260815_0001
Revises:
Create Date: 2026-08-15 00:00:00
"""

from collections.abc import Sequence

revision: str = "20260815_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish an Alembic baseline before domain tables are introduced."""


def downgrade() -> None:
    """Remove the baseline; there are no database objects yet."""
