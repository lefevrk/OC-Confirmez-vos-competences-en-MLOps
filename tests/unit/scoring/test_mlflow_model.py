"""Tests for the startup-only MLflow adapter."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from api.infra.config import Settings
from api.infra.mlflow_model import MlflowScoringModel, load_champion


class FakeInferenceSession:
    """In-memory ONNX Runtime session returning two class probabilities."""

    def get_inputs(self):
        """Declare a single float input, matching the feature used in these tests."""
        return [SimpleNamespace(name="payment_credit_ratio", type="tensor(float)")]

    def run(self, output_names, feed):
        """Return the positive class in the second output position."""
        return [np.array([[0.91, 0.09]])]


def _patch_mlflow(
    monkeypatch, *, threshold_path, registered_model_version, model_dir=None, session=None
):
    """Wire every MLflow/onnxruntime call the adapter makes to test doubles."""
    mlflow_runtime = Mock()
    model_registry_client = Mock()
    model_registry_client.get_model_version_by_alias.return_value = registered_model_version
    monkeypatch.setattr(
        "api.infra.mlflow_model.MlflowClient", Mock(return_value=model_registry_client)
    )
    monkeypatch.setattr("api.infra.mlflow_model.mlflow", mlflow_runtime)

    def fake_download_artifacts(artifact_uri):
        """Route the threshold-artifact vs model-directory downloads separately."""
        return str(threshold_path) if artifact_uri.endswith("threshold.json") else str(model_dir)

    monkeypatch.setattr(
        "api.infra.mlflow_model.download_artifacts", Mock(side_effect=fake_download_artifacts)
    )
    monkeypatch.setattr(
        "api.infra.mlflow_model.ort.InferenceSession",
        Mock(return_value=session or FakeInferenceSession()),
    )
    return mlflow_runtime, model_registry_client


def test_load_champion_builds_adapter_from_registered_version(monkeypatch, tmp_path) -> None:
    """Build an adapter from the registered champion and its threshold artifact."""
    threshold_path = tmp_path / "threshold.json"
    threshold_path.write_text('{"optimal_threshold": 0.09}')
    model_dir = tmp_path / "model_dir"
    model_dir.mkdir()
    (model_dir / "model.onnx").touch()
    registered_model_version = SimpleNamespace(version="3", run_id="run-123")
    session = FakeInferenceSession()

    mlflow_runtime, model_registry_client = _patch_mlflow(
        monkeypatch,
        threshold_path=threshold_path,
        registered_model_version=registered_model_version,
        model_dir=model_dir,
        session=session,
    )
    monkeypatch.delenv("MLFLOW_TRACKING_USERNAME", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_PASSWORD", raising=False)

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        mlflow_tracking_uri="https://mlflow.example",
        mlflow_tracking_username="username",
        mlflow_tracking_password="password",
    )

    scoring_model = load_champion(settings)

    assert scoring_model == MlflowScoringModel(
        session=session,  # type: ignore[arg-type]
        version="3",
        threshold=0.09,
    )
    mlflow_runtime.set_tracking_uri.assert_called_once_with("https://mlflow.example")
    model_registry_client.get_model_version_by_alias.assert_called_once_with(
        "credit_scoring", "champion"
    )
    assert os.environ["MLFLOW_TRACKING_USERNAME"] == "username"
    assert os.environ["MLFLOW_TRACKING_PASSWORD"] == "password"


def test_load_champion_rejects_threshold_outside_unit_range(monkeypatch, tmp_path) -> None:
    """A corrupted threshold artifact must not silently accept-all or refuse-all."""
    threshold_path = tmp_path / "threshold.json"
    threshold_path.write_text('{"optimal_threshold": 87}')
    registered_model_version = SimpleNamespace(version="3", run_id="run-123")
    _patch_mlflow(
        monkeypatch,
        threshold_path=threshold_path,
        registered_model_version=registered_model_version,
    )

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        mlflow_tracking_uri="https://mlflow.example",
        mlflow_tracking_username="username",
        mlflow_tracking_password="password",
    )

    with pytest.raises(RuntimeError, match=r"outside the \[0, 1\] range"):
        load_champion(settings)


def test_load_champion_rejects_a_version_without_a_source_run(monkeypatch) -> None:
    """A registered version with no source run has no threshold artifact to fetch."""
    registered_model_version = SimpleNamespace(version="3", run_id=None)
    monkeypatch.setattr(
        "api.infra.mlflow_model.MlflowClient",
        Mock(
            return_value=Mock(
                get_model_version_by_alias=Mock(return_value=registered_model_version)
            )
        ),
    )
    monkeypatch.setattr("api.infra.mlflow_model.mlflow", Mock())

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        mlflow_tracking_uri="https://mlflow.example",
        mlflow_tracking_username="username",
        mlflow_tracking_password="password",
    )

    with pytest.raises(RuntimeError, match="no source run"):
        load_champion(settings)


def test_probability_returns_the_positive_class_probability() -> None:
    """Return the positive class from the ONNX session's two-column output."""
    model = MlflowScoringModel(
        session=FakeInferenceSession(),  # type: ignore[arg-type]
        version="3",
        threshold=0.09,
    )
    assert model.probability({"payment_credit_ratio": 0.1}) == 0.09
