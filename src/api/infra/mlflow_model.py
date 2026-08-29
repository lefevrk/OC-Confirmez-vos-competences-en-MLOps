"""MLflow adapter used only during FastAPI startup."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from loguru import logger
import mlflow
from mlflow.artifacts import download_artifacts
from mlflow.tracking import MlflowClient
import numpy as np
import onnxruntime as ort

from api.infra.config import Settings


def _feature_tensor(value: Any, onnx_type: str) -> np.ndarray:
    """Cast one feature value to the shape/dtype its ONNX input tensor declares."""
    if onnx_type == "tensor(string)":
        return np.array([[str(value)]], dtype=object)
    return np.array([[value]], dtype=np.float32)


@dataclass(frozen=True)
class MlflowScoringModel:
    """ONNX Runtime session for the champion, and the threshold logged by its source run.

    Loaded directly via `onnxruntime` rather than `mlflow.pyfunc`: the
    champion's ONNX graph declares one named input tensor per feature (mixed
    float/string types), a shape MLflow's built-in ONNX pyfunc wrapper does
    not marshal correctly from a DataFrame or dict — reproduced against the
    real model as `INVALID_ARGUMENT: Unexpected input data type`. See
    docs/operations/optimisation-inference.md for the full trade-off.
    """

    session: ort.InferenceSession
    version: str
    threshold: float

    def probability(self, features: dict[str, Any]) -> float:
        """Score in memory; this method intentionally makes no MLflow call."""
        feed = {
            input_meta.name: _feature_tensor(features[input_meta.name], input_meta.type)
            for input_meta in self.session.get_inputs()
        }
        (probabilities,) = self.session.run(None, feed)
        return float(np.asarray(probabilities)[0][1])


def load_champion(settings: Settings) -> MlflowScoringModel:
    """Fetch model, version and threshold exactly once at startup."""
    os.environ["MLFLOW_TRACKING_USERNAME"] = settings.mlflow_tracking_username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = settings.mlflow_tracking_password
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    model_registry_client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)

    logger.bind(model_name=settings.model_name, model_alias=settings.model_alias).debug(
        "mlflow_champion_resolution_started"
    )
    registered_model_version = model_registry_client.get_model_version_by_alias(
        settings.model_name,
        settings.model_alias,
    )
    source_run_id = registered_model_version.run_id

    if source_run_id is None:
        raise RuntimeError("The registered model version has no source run")

    logger.bind(run_id=source_run_id).debug("mlflow_threshold_artifact_download_started")
    threshold_artifact_path = download_artifacts(
        artifact_uri=f"runs:/{source_run_id}/threshold.json"
    )
    threshold_artifact = json.loads(Path(threshold_artifact_path).read_text())
    threshold = float(threshold_artifact["optimal_threshold"])
    if not 0 <= threshold <= 1:
        raise RuntimeError(f"Champion threshold {threshold} is outside the [0, 1] range")

    logger.bind(run_id=source_run_id).debug("mlflow_onnx_model_load_started")
    model_dir = Path(
        download_artifacts(artifact_uri=f"models:/{settings.model_name}@{settings.model_alias}")
    )
    onnx_path = next(model_dir.glob("*.onnx"))
    session = ort.InferenceSession(str(onnx_path))

    model_version = str(registered_model_version.version)
    logger.bind(model_version=model_version, threshold=threshold).info("mlflow_champion_loaded")

    return MlflowScoringModel(
        session=session,
        version=model_version,
        threshold=threshold,
    )
