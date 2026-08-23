"""Integration tests for the drift-analysis Postgres export.

Runs against the real, migrated PostgreSQL container started once for the
whole test session (see conftest.py) — not a mock, not SQLite.
"""

from datetime import datetime, timedelta, timezone

import pytest
from scripts.export_tracking_for_drift import export_predictions
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from api.infra.config import get_settings
from api.infra.postgres.models import PredictionEventRecord


@pytest.fixture
def engine():
    """Connect to the session's PostgreSQL container."""
    instance = create_engine(get_settings().database_url)
    yield instance
    with instance.begin() as connection:
        connection.execute(delete(PredictionEventRecord))


def _record(
    prediction_id: str, occurred_at: datetime, feature_value: float
) -> PredictionEventRecord:
    return PredictionEventRecord(
        prediction_id=prediction_id,
        occurred_at=occurred_at,
        model_name="credit_scoring",
        model_alias="champion",
        model_version="3",
        status="success",
        probability=0.5,
        decision=0,
        inference_latency_ms=10.0,
        features={"ext_source_2": feature_value, "code_gender": "F"},
    )


def test_export_predictions_unpacks_features_into_flat_columns(engine) -> None:
    """Each JSONB feature becomes its own DataFrame column."""
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add(_record("11111111-1111-1111-1111-111111111111", now, 0.7))
        session.commit()

    dataset = export_predictions(get_settings().database_url)

    assert len(dataset) == 1
    row = dataset.iloc[0]
    assert row["ext_source_2"] == pytest.approx(0.7)
    assert row["code_gender"] == "F"
    assert row["status"] == "success"
    assert row["probability"] == pytest.approx(0.5)


def test_export_predictions_filters_by_occurred_at_window(engine) -> None:
    """Rows outside the requested window are excluded."""
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(hours=2)
    with Session(engine) as session:
        session.add(_record("22222222-2222-2222-2222-222222222222", earlier, 0.1))
        session.add(_record("33333333-3333-3333-3333-333333333333", now, 0.9))
        session.commit()

    dataset = export_predictions(
        get_settings().database_url,
        start=now - timedelta(minutes=1),
        end=now + timedelta(minutes=1),
    )

    assert len(dataset) == 1
    assert dataset.iloc[0]["ext_source_2"] == pytest.approx(0.9)
