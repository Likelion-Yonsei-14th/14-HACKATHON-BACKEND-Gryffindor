"""Store fixed KRW product prices and estimated refund amounts.

Revision ID: 20260817_0005
Revises: 20260817_0004
Create Date: 2026-08-17 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0005"
down_revision: str | Sequence[str] | None = "20260817_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_products_retail_price_nonnegative",
        "products",
        type_="check",
    )
    op.alter_column(
        "products",
        "retail_price_krw",
        new_column_name="price_krw",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.add_column(
        "products",
        sa.Column(
            "estimated_refund_krw",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("products", "estimated_refund_krw", server_default=None)
    op.create_check_constraint(
        "ck_products_price_nonnegative",
        "products",
        "price_krw >= 0",
    )
    op.create_check_constraint(
        "ck_products_estimated_refund_nonnegative",
        "products",
        "estimated_refund_krw >= 0",
    )
    op.create_check_constraint(
        "ck_products_estimated_refund_not_above_price",
        "products",
        "estimated_refund_krw <= price_krw",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_products_estimated_refund_not_above_price",
        "products",
        type_="check",
    )
    op.drop_constraint(
        "ck_products_estimated_refund_nonnegative",
        "products",
        type_="check",
    )
    op.drop_constraint(
        "ck_products_price_nonnegative",
        "products",
        type_="check",
    )
    op.drop_column("products", "estimated_refund_krw")
    op.alter_column(
        "products",
        "price_krw",
        new_column_name="retail_price_krw",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_products_retail_price_nonnegative",
        "products",
        "retail_price_krw >= 0",
    )
