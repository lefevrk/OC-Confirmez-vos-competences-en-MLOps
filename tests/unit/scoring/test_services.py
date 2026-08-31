"""Unit tests for dependency-free scoring behavior."""

from typing import Any

from loguru import logger
import pytest

from api.modules.scoring.domain.entities import PredictionEvent
from api.modules.scoring.domain.errors import InvalidProbabilityError, PredictionPersistenceError
from api.modules.scoring.services.predict import predict


class FakeModel:
    """Deterministic in-memory scoring model."""

    version = "3"
    threshold = 0.7

    def __init__(self, probability: float = 0.8) -> None:
        """Store the probability this fake model always returns."""
        self._probability = probability

    def probability(self, features: dict[str, Any]) -> float:
        """Return the configured probability."""
        del features
        return self._probability


class CrashingModel:
    """A model that fails outright, never returning a probability."""

    version = "3"
    threshold = 0.7

    def probability(self, features: dict[str, Any]) -> float:
        """Raise instead of scoring."""
        del features
        raise RuntimeError("model exploded")


class FakeRecorder:
    """In-memory prediction recorder, optionally simulating a storage failure."""

    def __init__(self, fails: bool = False) -> None:
        """Store whether record() should simulate a storage failure."""
        self._fails = fails
        self.recorded: list[tuple[PredictionEvent, dict[str, Any]]] = []

    def record(self, event: PredictionEvent, features: dict[str, Any]) -> None:
        """Append the event, or raise if this recorder simulates a failure."""
        if self._fails:
            raise RuntimeError("storage unavailable")
        self.recorded.append((event, features))


def test_predict_applies_the_model_threshold() -> None:
    """The use case produces both probability and decision."""
    result = predict(FakeModel(probability=0.8), FakeRecorder(), {"feature": 1.0})
    assert result.prediction_id
    assert result.probability == 0.8
    assert result.decision == 1
    assert result.model_version == "3"
    assert result.inference_latency_ms >= 0


def test_predict_rejects_the_prediction_below_threshold() -> None:
    """A probability under the threshold decides against the positive class."""
    result = predict(FakeModel(probability=0.6), FakeRecorder(), {"feature": 1.0})
    assert result.decision == 0


def test_predict_accepts_the_prediction_at_the_threshold() -> None:
    """A probability equal to the threshold decides for the positive class (the '>=' rule)."""
    result = predict(FakeModel(probability=0.7), FakeRecorder(), {"feature": 1.0})
    assert result.decision == 1


def test_predict_rejects_a_probability_outside_the_valid_range() -> None:
    """A model returning a value outside [0, 1] is a hard failure, not a silent decision."""
    with pytest.raises(InvalidProbabilityError):
        predict(FakeModel(probability=1.5), FakeRecorder(), {"feature": 1.0})


def test_predict_records_the_completed_prediction() -> None:
    """A successful prediction is handed to the recorder as a 'success' event."""
    recorder = FakeRecorder()
    features = {"feature": 1.0}
    result = predict(FakeModel(probability=0.8), recorder, features)

    assert len(recorder.recorded) == 1
    event, recorded_features = recorder.recorded[0]
    assert event.status == "success"
    assert event.error_code is None
    assert event.prediction_id == result.prediction_id
    assert event.probability == result.probability
    assert event.decision == result.decision
    assert recorded_features == features


def test_predict_wraps_a_recorder_failure_on_success_in_a_domain_error() -> None:
    """A storage failure on the success path is a hard failure, never a dropped event."""
    with pytest.raises(PredictionPersistenceError):
        predict(FakeModel(probability=0.8), FakeRecorder(fails=True), {"feature": 1.0})


def test_predict_records_a_failed_scoring_attempt() -> None:
    """An unexpected model crash is still recorded, with the fields it never reached unset."""
    recorder = FakeRecorder()
    with pytest.raises(RuntimeError, match="model exploded"):
        predict(CrashingModel(), recorder, {"feature": 1.0})

    assert len(recorder.recorded) == 1
    event, features = recorder.recorded[0]
    assert event.status == "error"
    assert event.error_code == "RuntimeError"
    assert event.probability is None
    assert event.decision is None
    assert event.inference_latency_ms is None
    assert features == {"feature": 1.0}


def test_predict_records_an_invalid_probability_as_a_failed_attempt() -> None:
    """An out-of-range probability is recorded as a failure, keeping what the model returned."""
    recorder = FakeRecorder()
    with pytest.raises(InvalidProbabilityError):
        predict(FakeModel(probability=1.5), recorder, {"feature": 1.0})

    assert len(recorder.recorded) == 1
    event, _ = recorder.recorded[0]
    assert event.status == "error"
    assert event.error_code == "InvalidProbabilityError"
    assert event.probability == 1.5
    assert event.decision is None
    assert event.inference_latency_ms is not None


def test_predict_does_not_mask_the_original_error_when_recording_the_failure_also_fails() -> None:
    """A storage failure while recording a failed attempt must not hide the real error."""
    with pytest.raises(RuntimeError, match="model exploded"):
        predict(CrashingModel(), FakeRecorder(fails=True), {"feature": 1.0})


def test_predict_logs_the_completed_scoring_event() -> None:
    """A successful prediction emits a bound, structured log record."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(message.record["message"]), level="INFO")
    try:
        predict(FakeModel(probability=0.8), FakeRecorder(), {"feature": 1.0})
    finally:
        logger.remove(sink_id)

    assert "scoring_completed" in records


def test_predict_binds_the_same_prediction_id_across_its_log_lines() -> None:
    """The started and completed events correlate to the same returned prediction_id."""
    prediction_ids: list[str] = []
    sink_id = logger.add(
        lambda message: prediction_ids.append(message.record["extra"]["prediction_id"]),
        level="DEBUG",
    )
    try:
        result = predict(FakeModel(probability=0.8), FakeRecorder(), {"feature": 1.0})
    finally:
        logger.remove(sink_id)

    assert set(prediction_ids) == {result.prediction_id}


def test_predict_gives_identical_inputs_the_same_fingerprint_but_different_ids() -> None:
    """input_hash is deterministic for a given payload; prediction_id never is."""
    model = FakeModel(probability=0.8)
    features = {"feature": 1.0}
    fingerprints: list[str] = []
    sink_id = logger.add(
        lambda message: fingerprints.append(message.record["extra"]["input_hash"]),
        level="INFO",
    )
    try:
        first = predict(model, FakeRecorder(), features)
        second = predict(model, FakeRecorder(), features)
    finally:
        logger.remove(sink_id)

    assert first.prediction_id != second.prediction_id
    assert fingerprints == [fingerprints[0], fingerprints[0]]


def test_predict_gives_different_inputs_different_fingerprints() -> None:
    """input_hash distinguishes payloads instead of collapsing them together."""
    model = FakeModel(probability=0.8)
    fingerprints: list[str] = []
    sink_id = logger.add(
        lambda message: fingerprints.append(message.record["extra"]["input_hash"]),
        level="INFO",
    )
    try:
        predict(model, FakeRecorder(), {"feature": 1.0})
        predict(model, FakeRecorder(), {"feature": 2.0})
    finally:
        logger.remove(sink_id)

    assert fingerprints[0] != fingerprints[1]
