"""Add demo-user personalization, document extraction, and store catalog relations.

Revision ID: 20260819_0007
Revises: 20260817_0006
Create Date: 2026-08-19 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0007"
down_revision: str | Sequence[str] | None = "20260817_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    users_table = op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(users_table, [{"id": 1, "name": "Demo User"}])

    op.add_column(
        "shopping_sessions",
        sa.Column("user_id", sa.Integer(), server_default=sa.text("1"), nullable=True),
    )
    shopping_sessions = sa.table("shopping_sessions", sa.column("user_id", sa.Integer()))
    op.execute(sa.update(shopping_sessions).values(user_id=1))
    op.alter_column(
        "shopping_sessions",
        "user_id",
        existing_type=sa.Integer(),
        server_default=sa.text("1"),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_shopping_sessions_user_id_users",
        "shopping_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "wishlist_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_wishlist_items_user_product"),
    )

    op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("store_name", sa.String(length=255), nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_amount", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "total_amount IS NULL OR total_amount >= 0",
            name="ck_receipts_total_amount_nonnegative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "flights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("departure_airport", sa.String(length=3), nullable=False),
        sa.Column("arrival_airport", sa.String(length=3), nullable=False),
        sa.Column("flight_number", sa.String(length=20), nullable=True),
        sa.Column("departure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "receipt_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("price", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_receipt_items_price_nonnegative",
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_receipt_items_quantity_positive",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "store_products",
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("store_id", "product_id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO store_products (store_id, product_id) "
            "SELECT stores.id, products.id FROM stores CROSS JOIN products"
        )
    )


def downgrade() -> None:
    op.drop_table("store_products")
    op.drop_table("receipt_items")
    op.drop_table("flights")
    op.drop_table("receipts")
    op.drop_table("wishlist_items")
    op.drop_constraint(
        "fk_shopping_sessions_user_id_users",
        "shopping_sessions",
        type_="foreignkey",
    )
    op.drop_column("shopping_sessions", "user_id")
    op.drop_table("users")
