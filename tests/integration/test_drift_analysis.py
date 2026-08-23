"""Integration tests for scripts/drift_analysis.py's production sampling.

Runs against the real, migrated PostgreSQL container started once for the
whole test session (see conftest.py) — not a mock, not SQLite.
"""

from datetime import datetime, timedelta, timezone

import pytest
from scripts.drift_analysis import sample_recent_production
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
        features={"ext_source_2": feature_value},
    )


def test_sample_recent_production_rejects_an_empty_table(engine) -> None:
    """A clear error, not a downstream pandas KeyError, when there's no traffic yet."""
    with pytest.raises(RuntimeError, match="prediction_events is empty"):
        sample_recent_production(get_settings().database_url, sample_size=5)


def test_sample_recent_production_returns_only_the_most_recent_rows(engine) -> None:
    """Only the `sample_size` most recent rows are returned, oldest excluded."""
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add(_record("11111111-1111-1111-1111-111111111111", now - timedelta(hours=1), 0.1))
        session.add(_record("22222222-2222-2222-2222-222222222222", now, 0.9))
        session.commit()

    dataset = sample_recent_production(get_settings().database_url, sample_size=1)

    assert len(dataset) == 1
    assert dataset.iloc[0]["ext_source_2"] == pytest.approx(0.9)
