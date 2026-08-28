"""Integration tests for the Gradio demo mounted on "/"."""

from fastapi.testclient import TestClient

from api.app import app
import api.infra.config as config_module


class _Model:
    """Minimal startup model."""

    version = "1"


class _Recorder:
    """A prediction recorder that reports ready without touching real storage."""

    def ready(self) -> bool:
        """Report readiness without touching real storage."""
        return True


def _bootstrap_ok(monkeypatch) -> None:
    monkeypatch.setattr("api.bootstrap.load_champion", lambda _settings: _Model())
    monkeypatch.setattr("api.bootstrap.connect_prediction_recorder", lambda _settings: _Recorder())


def test_root_serves_the_demo_without_a_token_configured(monkeypatch) -> None:
    """No API_TOKEN configured means auth is disabled, same as GET /evidently."""
    _bootstrap_ok(monkeypatch)
    monkeypatch.setenv("API_TOKEN", "")
    monkeypatch.setattr(config_module, "_settings", None)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    monkeypatch.setattr(config_module, "_settings", None)


def test_root_requires_credentials_once_a_token_is_configured(monkeypatch) -> None:
    """A configured API_TOKEN gates "/" behind HTTP Basic Auth."""
    _bootstrap_ok(monkeypatch)
    monkeypatch.setenv("API_TOKEN", "s3cret")
    monkeypatch.setattr(config_module, "_settings", None)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 401
    monkeypatch.setattr(config_module, "_settings", None)


def test_root_rejects_the_wrong_password(monkeypatch) -> None:
    """A wrong password is rejected the same as no credentials at all."""
    _bootstrap_ok(monkeypatch)
    monkeypatch.setenv("API_TOKEN", "s3cret")
    monkeypatch.setattr(config_module, "_settings", None)

    with TestClient(app) as client:
        response = client.get("/", auth=("anything", "wrong"))

    assert response.status_code == 401
    monkeypatch.setattr(config_module, "_settings", None)


def test_root_succeeds_with_the_correct_password(monkeypatch) -> None:
    """The username is unchecked — only the password (API_TOKEN) matters."""
    _bootstrap_ok(monkeypatch)
    monkeypatch.setenv("API_TOKEN", "s3cret")
    monkeypatch.setattr(config_module, "_settings", None)

    with TestClient(app) as client:
        response = client.get("/", auth=("anything", "s3cret"))

    assert response.status_code == 200
    monkeypatch.setattr(config_module, "_settings", None)


def test_existing_routes_stay_reachable_once_the_demo_is_mounted_on_root(monkeypatch) -> None:
    """Routes registered before the Gradio mount keep priority over its catch-all."""
    _bootstrap_ok(monkeypatch)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200
    monkeypatch.setattr(config_module, "_settings", None)
