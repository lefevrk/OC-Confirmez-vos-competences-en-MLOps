"""Integration tests for the Gradio demo mounted on "/"."""

from fastapi.testclient import TestClient

from api.app import app


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


def test_root_serves_the_demo(monkeypatch) -> None:
    """The demo root route serves the Gradio UI, open to anyone — see docs/design/security.md."""
    _bootstrap_ok(monkeypatch)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200


def test_existing_routes_stay_reachable_once_the_demo_is_mounted_on_root(monkeypatch) -> None:
    """Routes registered before the Gradio mount keep priority over its catch-all."""
    _bootstrap_ok(monkeypatch)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200
