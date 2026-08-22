"""Infrastructure routes are available without an MLflow server."""

import re

from fastapi.testclient import TestClient

from api.app import app


def test_liveness_does_not_require_dependencies(monkeypatch) -> None:
    """Health stays available when the model registry cannot be reached."""
    monkeypatch.setattr(
        "api.bootstrap.load_champion", lambda _settings: (_ for _ in ()).throw(RuntimeError())
    )
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"model": "error", "database": "ok"},
    }


class Model:
    """Minimal startup model."""

    version = "1"


class Recorder:
    """A prediction recorder that reports ready without touching real storage."""

    def ready(self) -> bool:
        """Report readiness without touching real storage."""
        return True


class UnavailableRecorder(Recorder):
    """A prediction recorder simulating a database that has gone down."""

    def ready(self) -> bool:
        """Simulate a database no longer reachable after startup."""
        raise RuntimeError("connection lost")


def test_readiness_reports_ready_once_the_model_and_database_are_available(monkeypatch) -> None:
    """Readiness succeeds once the startup model and database are both available."""
    monkeypatch.setattr("api.bootstrap.load_champion", lambda _settings: Model())
    monkeypatch.setattr("api.bootstrap.connect_prediction_recorder", lambda _settings: Recorder())
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.json() == {
        "status": "ready",
        "checks": {"model": "ok", "database": "ok"},
    }


def test_readiness_reports_degraded_when_the_database_is_unavailable(monkeypatch) -> None:
    """A database that fails its live check must fail readiness, even if the model loaded."""
    monkeypatch.setattr("api.bootstrap.load_champion", lambda _settings: Model())
    monkeypatch.setattr(
        "api.bootstrap.connect_prediction_recorder", lambda _settings: UnavailableRecorder()
    )
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"model": "ok", "database": "error"},
    }


def test_metrics_endpoint_exposes_prometheus_text(monkeypatch) -> None:
    """/metrics is scrapeable and reflects HTTP traffic already served."""
    monkeypatch.setattr("api.bootstrap.load_champion", lambda _settings: Model())
    monkeypatch.setattr("api.bootstrap.connect_prediction_recorder", lambda _settings: Recorder())
    with TestClient(app) as client:
        client.get("/health")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert re.search(
        r'credit_scoring_http_requests_total\{endpoint="/health",method="GET",'
        r'status_code="200"\} \d',
        response.text,
    )
    assert (
        'credit_scoring_model_info{model_alias="champion",model_version="1"} 1.0' in response.text
    )


def test_startup_reports_a_degraded_readiness_when_settings_are_invalid(monkeypatch) -> None:
    """A misconfigured environment fails startup without crashing the process."""
    monkeypatch.setattr(
        "api.bootstrap.get_settings", lambda: (_ for _ in ()).throw(RuntimeError("bad env"))
    )
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"model": "error", "database": "error"},
    }
