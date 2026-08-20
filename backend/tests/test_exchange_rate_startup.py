from fastapi.testclient import TestClient
from pytest import MonkeyPatch

import app.main as main_module
from app.core.config import Settings


def test_application_checks_exchange_rates_during_startup(monkeypatch: MonkeyPatch) -> None:
    checked_settings: list[Settings] = []
    settings = Settings(app_env="test", recognition_provider="scripted")

    def record_startup_check(received_settings: Settings) -> None:
        checked_settings.append(received_settings)

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        main_module,
        "_refresh_exchange_rates_on_startup",
        record_startup_check,
    )

    with TestClient(main_module.create_app()) as client:
        assert client.get("/health").status_code == 200

    assert checked_settings == [settings]


def test_application_can_disable_startup_check_for_isolated_tests(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_if_called(_: Settings) -> None:
        raise AssertionError("startup check must be disabled")

    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: Settings(app_env="test", recognition_provider="scripted"),
    )
    monkeypatch.setattr(
        main_module,
        "_refresh_exchange_rates_on_startup",
        fail_if_called,
    )

    with TestClient(main_module.create_app(enable_exchange_rate_startup=False)) as client:
        assert client.get("/health").status_code == 200
