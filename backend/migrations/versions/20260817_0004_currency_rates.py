"""Add the daily KRW exchange-rate cache.

Revision ID: 20260817_0004
Revises: 20260817_0003
Create Date: 2026-08-17 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0004"
down_revision: str | Sequence[str] | None = "20260817_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "currency_rates",
        sa.Column("base_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("target_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("base_currency = 'KRW'", name="ck_currency_rates_base_krw"),
        sa.CheckConstraint(
            "target_currency IN ('USD', 'CNY')",
            name="ck_currency_rates_target_supported",
        ),
        sa.CheckConstraint("rate > 0", name="ck_currency_rates_rate_positive"),
        sa.PrimaryKeyConstraint(
            "base_currency",
            "target_currency",
            name="pk_currency_rates",
        ),
    )


def downgrade() -> None:
    op.drop_table("currency_rates")
