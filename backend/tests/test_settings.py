from pytest import MonkeyPatch

from app.core.config import Settings


def test_settings_can_be_overridden_by_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@db:5432/test")

    settings = Settings()

    assert settings.app_env == "test"
    assert settings.database_url == "postgresql+psycopg://test:test@db:5432/test"


def test_openai_recognition_settings_can_be_overridden(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("RECOGNITION_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-key")
    monkeypatch.setenv("OPENAI_VISION_MODEL", "test-vision-model")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("RECOGNITION_MAX_CANDIDATES", "8")

    settings = Settings()

    assert settings.recognition_provider == "openai"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "secret-test-key"
    assert settings.openai_vision_model == "test-vision-model"
    assert settings.openai_timeout_seconds == 7.5
    assert settings.recognition_max_candidates == 8
