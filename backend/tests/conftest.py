from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models.currency_rate import CurrencyRate
from app.scripts.seed_products import seed_products


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with testing_session() as session:
        seed_products(session)
        session.add_all(
            [
                CurrencyRate(
                    base_currency="KRW",
                    target_currency="USD",
                    rate=Decimal("0.00072718"),
                    rate_date=date(2026, 8, 17),
                    last_checked_at=datetime(2026, 8, 17, tzinfo=UTC),
                ),
                CurrencyRate(
                    base_currency="KRW",
                    target_currency="CNY",
                    rate=Decimal("0.00505859"),
                    rate_date=date(2026, 8, 17),
                    last_checked_at=datetime(2026, 8, 17, tzinfo=UTC),
                ),
            ]
        )
        session.commit()
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def test_app(db_session: Session) -> Generator[FastAPI, None, None]:
    application = create_app(enable_exchange_rate_startup=False)
    test_settings = Settings(
        app_env="test",
        database_url="sqlite+pysqlite://",
        recognition_provider="mock",
        mock_recognition_status="MATCHED",
        mock_recognition_product_id="test_outer_001",
        recognition_max_image_bytes=5 * 1024 * 1024,
        recognition_max_candidates=20,
        openai_api_key=None,
    )

    def override_db_session() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_db_session
    application.dependency_overrides[get_settings] = lambda: test_settings
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(test_app) as test_client:
        yield test_client
