"""Integration tests for the /evidently drift-report route."""

from pathlib import Path

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


def _use_reports_dir(monkeypatch, reports_dir: Path) -> None:
    monkeypatch.setattr(config_module, "_settings", None)
    monkeypatch.setenv("REPORTS_DIR", str(reports_dir))


def test_drift_report_is_not_found_before_any_report_is_generated(
    monkeypatch, tmp_path: Path
) -> None:
    """No report has been generated into the reports directory yet."""
    _bootstrap_ok(monkeypatch)
    _use_reports_dir(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.get("/evidently")

    assert response.status_code == 404
    monkeypatch.setattr(config_module, "_settings", None)


def test_drift_report_is_served_once_generated(monkeypatch, tmp_path: Path) -> None:
    """A generated report is served as HTML from the configured reports directory."""
    _bootstrap_ok(monkeypatch)
    (tmp_path / "drift_report.html").write_text("<html>drift report</html>")
    _use_reports_dir(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.get("/evidently")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "drift report" in response.text
    monkeypatch.setattr(config_module, "_settings", None)


def test_drift_report_requires_a_token_once_one_is_configured(monkeypatch, tmp_path: Path) -> None:
    """The route is gated behind the same bearer-token auth as /predictions."""
    _bootstrap_ok(monkeypatch)
    (tmp_path / "drift_report.html").write_text("<html>drift report</html>")
    _use_reports_dir(monkeypatch, tmp_path)
    monkeypatch.setenv("API_TOKEN", "s3cret")

    with TestClient(app) as client:
        response = client.get("/evidently")

    assert response.status_code == 401
    monkeypatch.setattr(config_module, "_settings", None)


def test_drift_report_succeeds_with_the_correct_token(monkeypatch, tmp_path: Path) -> None:
    """The right Bearer token grants access to the drift report."""
    _bootstrap_ok(monkeypatch)
    (tmp_path / "drift_report.html").write_text("<html>drift report</html>")
    _use_reports_dir(monkeypatch, tmp_path)
    monkeypatch.setenv("API_TOKEN", "s3cret")

    with TestClient(app) as client:
        response = client.get("/evidently", headers={"Authorization": "Bearer s3cret"})

    assert response.status_code == 200
    monkeypatch.setattr(config_module, "_settings", None)
