from importlib import import_module
from typing import Protocol, cast
from uuid import UUID

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, MetaData, String, Table, Uuid, create_engine, insert, select


class StoreIsActiveMigration(Protocol):
    op: Operations

    def upgrade(self) -> None: ...

    def downgrade(self) -> None: ...


def _migration_module() -> StoreIsActiveMigration:
    module = import_module("migrations.versions.20260820_0012_store_is_active")
    return cast(StoreIsActiveMigration, module)


def test_store_is_active_migration_defaults_existing_rows_and_deactivates_legacy_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite://")
    metadata = MetaData()
    stores = Table(
        "stores",
        metadata,
        Column[UUID]("id", Uuid, primary_key=True),
        Column[str]("name", String(255), nullable=False),
    )
    metadata.create_all(engine)
    production_store_id = UUID("10000000-0000-0000-0000-000000000001")
    legacy_store_ids = (
        UUID("10000000-0000-0000-0000-000000000002"),
        UUID("10000000-0000-0000-0000-000000000003"),
    )
    other_existing_store_id = UUID("10000000-0000-0000-0000-000000000004")

    with engine.begin() as connection:
        connection.execute(
            insert(stores),
            [
                {"id": production_store_id, "name": "Reused production Store"},
                {"id": legacy_store_ids[0], "name": "MCM New York"},
                {"id": legacy_store_ids[1], "name": "MCM Airport Store"},
                {"id": other_existing_store_id, "name": "Existing Store"},
            ],
        )
        migration = _migration_module()
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )

        migration.upgrade()

        migrated_stores = Table("stores", MetaData(), autoload_with=connection)
        active_by_id = {
            UUID(str(store_id)): is_active
            for store_id, is_active in connection.execute(
                select(migrated_stores.c.id, migrated_stores.c.is_active)
            ).all()
        }
        assert active_by_id[production_store_id] is True
        assert active_by_id[other_existing_store_id] is True
        assert all(active_by_id[store_id] is False for store_id in legacy_store_ids)

        migration.downgrade()
        downgraded_stores = Table("stores", MetaData(), autoload_with=connection)
        assert "is_active" not in downgraded_stores.c

    engine.dispose()
