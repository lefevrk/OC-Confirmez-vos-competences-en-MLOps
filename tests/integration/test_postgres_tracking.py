"""Integration tests for the PostgreSQL prediction-event adapter.

Runs against the real, migrated PostgreSQL container started once for the
whole test session (see conftest.py) — not a mock, not SQLite.
"""

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DataError, OperationalError

from api.common.config import get_settings
from api.infra.postgres.models import PredictionEventRecord
from api.infra.postgres.tracking import PostgresPredictionRecorder
from api.modules.scoring.domain.entities import PredictionEvent


@pytest.fixture
def recorder():
    """Connect to the session's PostgreSQL container."""
    instance = PostgresPredictionRecorder(
        get_settings().database_url, model_name="credit_scoring", model_alias="champion"
    )
    yield instance
    with instance.engine.begin() as connection:
        connection.execute(delete(PredictionEventRecord))


def test_ready_reports_a_reachable_database(recorder: PostgresPredictionRecorder) -> None:
    """A live connection reports ready."""
    assert recorder.ready() is True


def test_ready_raises_against_an_unreachable_database() -> None:
    """An unreachable host fails loudly instead of silently reporting ready."""
    unreachable = PostgresPredictionRecorder(
        "postgresql://postgres@localhost:1/nope",
        model_name="credit_scoring",
        model_alias="champion",
    )
    with pytest.raises(OperationalError):
        unreachable.ready()


def test_record_persists_a_successful_event_with_every_field_intact(
    recorder: PostgresPredictionRecorder,
) -> None:
    """A recorded success event is readable back with every field intact."""
    event = PredictionEvent(
        prediction_id="11111111-1111-1111-1111-111111111111",
        model_version="3",
        status="success",
        probability=0.42,
        decision=0,
        inference_latency_ms=12.5,
        error_code=None,
    )
    features = {"days_birth": -12000, "code_gender": "F"}

    recorder.record(event, features)

    with recorder.engine.connect() as connection:
        row = connection.execute(
            select(PredictionEventRecord).where(
                PredictionEventRecord.prediction_id == event.prediction_id
            )
        ).one()

    assert row.model_name == "credit_scoring"
    assert row.model_alias == "champion"
    assert row.model_version == "3"
    assert row.status == "success"
    assert row.error_code is None
    assert row.probability == pytest.approx(0.42)
    assert row.decision == 0
    assert row.inference_latency_ms == pytest.approx(12.5)
    assert row.features == features
    assert row.occurred_at is not None


def test_record_persists_a_failed_event_with_null_scoring_fields(
    recorder: PostgresPredictionRecorder,
) -> None:
    """A model crash still leaves a readable row, with the fields it never reached unset."""
    event = PredictionEvent(
        prediction_id="33333333-3333-3333-3333-333333333333",
        model_version="3",
        status="error",
        probability=None,
        decision=None,
        inference_latency_ms=None,
        error_code="RuntimeError",
    )

    recorder.record(event, {"feature": 1.0})

    with recorder.engine.connect() as connection:
        row = connection.execute(
            select(PredictionEventRecord).where(
                PredictionEventRecord.prediction_id == event.prediction_id
            )
        ).one()

    assert row.status == "error"
    assert row.error_code == "RuntimeError"
    assert row.probability is None
    assert row.decision is None
    assert row.inference_latency_ms is None


def test_record_raises_and_logs_on_a_persistence_failure(
    recorder: PostgresPredictionRecorder,
) -> None:
    """A write the database itself rejects is a hard failure, not a silent no-op."""
    event = PredictionEvent(
        prediction_id="22222222-2222-2222-2222-222222222222",
        model_version="v" * 100,
        status="success",
        probability=0.1,
        decision=0,
        inference_latency_ms=1.0,
        error_code=None,
    )

    with pytest.raises(DataError):
        recorder.record(event, {"feature": 1.0})
