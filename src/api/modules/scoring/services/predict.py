"""Prediction use case with no FastAPI or MLflow dependency."""

import hashlib
import json
from time import perf_counter
from typing import TYPE_CHECKING, Any
import uuid

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger

from api.modules.scoring.domain.entities import Prediction, PredictionEvent
from api.modules.scoring.domain.errors import (
    InferenceError,
    InvalidProbabilityError,
    PredictionPersistenceError,
)
from api.modules.scoring.ports.model import ScoringModel
from api.modules.scoring.ports.prediction_recorder import PredictionRecorder


def _fingerprint(features: dict[str, Any]) -> str:
    """Return a short, one-way fingerprint of a feature payload — never the values."""
    raw = json.dumps(features, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _record_failure(
    recorder: PredictionRecorder,
    bound: "Logger",
    event: PredictionEvent,
    features: dict[str, Any],
) -> None:
    """Best-effort: the client already gets the real error regardless of this outcome."""
    try:
        recorder.record(event, features)
    except Exception as exc:
        bound.bind(error=str(exc)).error("prediction_event_persistence_failed")


def predict(
    model: ScoringModel, recorder: PredictionRecorder, features: dict[str, Any]
) -> Prediction:
    """Score a validated payload using the already-loaded model."""
    prediction_id = str(uuid.uuid4())
    bound = logger.bind(
        prediction_id=prediction_id,
        input_hash=_fingerprint(features),
        feature_count=len(features),
    )
    bound.debug("scoring_started")

    try:
        inference_started = perf_counter()
        probability = model.probability(features)
        inference_latency_ms = (perf_counter() - inference_started) * 1_000
    except Exception as exc:
        bound.bind(error=str(exc)).error("scoring_failed")
        _record_failure(
            recorder,
            bound,
            PredictionEvent(
                prediction_id=prediction_id,
                model_version=model.version,
                status="error",
                probability=None,
                decision=None,
                inference_latency_ms=None,
                error_code=type(exc).__name__,
            ),
            features,
        )
        raise InferenceError("The model failed to score the payload") from exc

    if not 0 <= probability <= 1:
        bound.bind(probability=probability).warning("invalid_probability_returned")
        _record_failure(
            recorder,
            bound,
            PredictionEvent(
                prediction_id=prediction_id,
                model_version=model.version,
                status="error",
                probability=probability,
                decision=None,
                inference_latency_ms=inference_latency_ms,
                error_code="InvalidProbabilityError",
            ),
            features,
        )
        raise InvalidProbabilityError("The model must return a probability between 0 and 1")

    prediction = Prediction(
        prediction_id=prediction_id,
        probability=probability,
        decision=int(probability >= model.threshold),
        model_version=model.version,
        inference_latency_ms=inference_latency_ms,
    )
    try:
        recorder.record(
            PredictionEvent(
                prediction_id=prediction.prediction_id,
                model_version=prediction.model_version,
                status="success",
                probability=prediction.probability,
                decision=prediction.decision,
                inference_latency_ms=prediction.inference_latency_ms,
                error_code=None,
            ),
            features,
        )
    except Exception as exc:
        bound.bind(error=str(exc)).error("prediction_event_persistence_failed")
        raise PredictionPersistenceError(
            "The prediction succeeded but could not be recorded"
        ) from exc
    bound.bind(
        probability=prediction.probability,
        decision=prediction.decision,
        model_version=prediction.model_version,
        inference_latency_ms=round(inference_latency_ms, 2),
    ).info("scoring_completed")
    return prediction
