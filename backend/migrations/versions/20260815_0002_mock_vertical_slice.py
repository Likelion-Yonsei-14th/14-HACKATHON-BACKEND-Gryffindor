"""Create mock vertical slice tables.

Revision ID: 20260815_0002
Revises: 20260815_0001
Create Date: 2026-08-15 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0002"
down_revision: str | Sequence[str] | None = "20260815_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

session_status = postgresql.ENUM("ACTIVE", "COMPLETED", name="session_status", create_type=False)
trigger_type = postgresql.ENUM(
    "OCCUPANCY",
    "DWELL",
    "OCCUPANCY_AND_DWELL",
    name="trigger_type",
    create_type=False,
)
purchase_state = postgresql.ENUM("UNSET", "PURCHASED", name="purchase_state", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    session_status.create(bind, checkfirst=True)
    trigger_type.create(bind, checkfirst=True)
    purchase_state.create(bind, checkfirst=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("retail_price_krw", sa.BigInteger(), nullable=False),
        sa.Column("tax_refund_supported", sa.Boolean(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("retail_price_krw >= 0", name="ck_products_retail_price_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_table(
        "shopping_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", session_status, nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "session_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_occupancy_ratio", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("max_dwell_ms", sa.Integer(), nullable=False),
        sa.Column("last_trigger_type", trigger_type, nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("purchase_state", purchase_state, nullable=False),
        sa.Column("interested", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "max_occupancy_ratio >= 0 AND max_occupancy_ratio <= 1",
            name="ck_session_products_occupancy_range",
        ),
        sa.CheckConstraint("max_dwell_ms >= 0", name="ck_session_products_dwell_nonnegative"),
        sa.CheckConstraint(
            "observation_count >= 1",
            name="ck_session_products_observation_count_positive",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["shopping_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "product_id",
            name="uq_session_products_session_product",
        ),
    )


def downgrade() -> None:
    op.drop_table("session_products")
    op.drop_table("shopping_sessions")
    op.drop_table("products")

    bind = op.get_bind()
    purchase_state.drop(bind, checkfirst=True)
    trigger_type.drop(bind, checkfirst=True)
    session_status.drop(bind, checkfirst=True)
