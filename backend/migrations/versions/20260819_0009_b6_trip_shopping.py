"""Add B6 trip shopping, hotel, location, and visit reservation data.

Revision ID: 20260819_0009
Revises: 20260819_0008
Create Date: 2026-08-19 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0009"
down_revision: str | Sequence[str] | None = "20260819_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("destination_city", sa.String(length=120), nullable=True),
        sa.Column("destination_country", sa.String(length=2), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trips_user_id"), "trips", ["user_id"], unique=False)

    op.add_column("flights", sa.Column("trip_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_flights_trip_id_trips",
        "flights",
        "trips",
        ["trip_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_flights_trip_id"), "flights", ["trip_id"], unique=False)

    op.alter_column(
        "stores",
        "city",
        existing_type=sa.String(length=120),
        nullable=True,
    )
    op.add_column("stores", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("stores", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("stores", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("stores", sa.Column("terminal", sa.String(length=100), nullable=True))
    op.add_column("stores", sa.Column("opening_hours", sa.Text(), nullable=True))

    op.create_table(
        "hotel_stays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_hotel_stays_latitude_range",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_hotel_stays_longitude_range",
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", name="uq_hotel_stays_trip_id"),
    )

    op.create_table(
        "visit_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('RESERVED', 'CANCELLED')",
            name="reservation_status",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_visit_reservations_trip_id"),
        "visit_reservations",
        ["trip_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_visit_reservations_user_id"),
        "visit_reservations",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "visit_reservation_products",
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["visit_reservations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("reservation_id", "product_id"),
    )


def downgrade() -> None:
    op.drop_table("visit_reservation_products")
    op.drop_index(op.f("ix_visit_reservations_user_id"), table_name="visit_reservations")
    op.drop_index(op.f("ix_visit_reservations_trip_id"), table_name="visit_reservations")
    op.drop_table("visit_reservations")
    op.drop_table("hotel_stays")
    op.drop_column("stores", "opening_hours")
    op.drop_column("stores", "terminal")
    op.drop_column("stores", "longitude")
    op.drop_column("stores", "latitude")
    op.drop_column("stores", "address")
    op.execute(sa.text("UPDATE stores SET city = 'Unknown' WHERE city IS NULL"))
    op.alter_column(
        "stores",
        "city",
        existing_type=sa.String(length=120),
        nullable=False,
    )
    op.drop_index(op.f("ix_flights_trip_id"), table_name="flights")
    op.drop_constraint("fk_flights_trip_id_trips", "flights", type_="foreignkey")
    op.drop_column("flights", "trip_id")
    op.drop_index(op.f("ix_trips_user_id"), table_name="trips")
    op.drop_table("trips")
