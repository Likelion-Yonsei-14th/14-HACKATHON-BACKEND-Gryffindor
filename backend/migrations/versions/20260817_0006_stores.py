"""Add stores and require each shopping session to reference one.

Revision ID: 20260817_0006
Revises: 20260817_0005
Create Date: 2026-08-17 18:00:00
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0006"
down_revision: str | Sequence[str] | None = "20260817_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEOUL_STORE_ID = UUID("10000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    stores_table = op.create_table(
        "stores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("airport_code", sa.String(length=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        stores_table,
        [
            {
                "id": SEOUL_STORE_ID,
                "name": "MCM Seoul",
                "brand": "MCM",
                "country": "KR",
                "city": "Seoul",
                "type": "CITY",
                "airport_code": None,
            },
            {
                "id": UUID("10000000-0000-0000-0000-000000000002"),
                "name": "MCM New York",
                "brand": "MCM",
                "country": "US",
                "city": "New York",
                "type": "CITY",
                "airport_code": None,
            },
            {
                "id": UUID("10000000-0000-0000-0000-000000000003"),
                "name": "MCM Airport Store",
                "brand": "MCM",
                "country": "KR",
                "city": "Incheon",
                "type": "AIRPORT",
                "airport_code": "ICN",
            },
        ],
    )

    op.add_column("shopping_sessions", sa.Column("store_id", sa.Uuid(), nullable=True))
    shopping_sessions = sa.table("shopping_sessions", sa.column("store_id", sa.Uuid()))
    op.execute(sa.update(shopping_sessions).values(store_id=SEOUL_STORE_ID))
    op.alter_column("shopping_sessions", "store_id", existing_type=sa.Uuid(), nullable=False)
    op.create_foreign_key(
        "fk_shopping_sessions_store_id_stores",
        "shopping_sessions",
        "stores",
        ["store_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_shopping_sessions_store_id_stores",
        "shopping_sessions",
        type_="foreignkey",
    )
    op.drop_column("shopping_sessions", "store_id")
    op.drop_table("stores")
