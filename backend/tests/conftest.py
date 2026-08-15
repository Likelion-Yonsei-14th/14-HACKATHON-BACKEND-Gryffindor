from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
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
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def test_app(db_session: Session) -> Generator[FastAPI, None, None]:
    application = create_app()

    def override_db_session() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_db_session
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(test_app) as test_client:
        yield test_client
