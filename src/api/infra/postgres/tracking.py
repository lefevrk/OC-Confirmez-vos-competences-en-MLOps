"""PostgreSQL adapter for prediction-event persistence."""

from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from api.common.config import Settings
from api.infra.postgres.models import PredictionEventRecord
from api.modules.scoring.domain.entities import PredictionEvent


@dataclass
class PostgresPredictionRecorder:
    """Own the service engine and persist every scoring attempt's outcome."""

    database_url: str
    model_name: str
    model_alias: str
    engine: Engine = field(init=False)

    def __post_init__(self) -> None:
        """Create the engine once; SQLAlchemy opens connections lazily.

        A short connect/statement timeout keeps a slow or unreachable
        database from stalling a request instead of failing it outright.
        """
        self.engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=3000"},
        )

    def ready(self) -> bool:
        """Verify the database connection without reading prediction data."""
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            logger.bind(error=str(exc)).error("postgres_readiness_check_failed")
            raise
        return True

    def record(self, event: PredictionEvent, features: dict[str, Any]) -> None:
        """Persist one prediction event — successful or not — in a transaction."""
        try:
            with Session(self.engine) as session:
                session.add(
                    PredictionEventRecord(
                        prediction_id=event.prediction_id,
                        model_name=self.model_name,
                        model_alias=self.model_alias,
                        model_version=event.model_version,
                        status=event.status,
                        error_code=event.error_code,
                        probability=event.probability,
                        decision=event.decision,
                        inference_latency_ms=event.inference_latency_ms,
                        features=features,
                    )
                )
                session.commit()
        except Exception as exc:
            logger.bind(prediction_id=event.prediction_id, error=str(exc)).error(
                "postgres_prediction_event_persistence_failed"
            )
            raise
        logger.bind(prediction_id=event.prediction_id, status=event.status).debug(
            "postgres_prediction_event_persisted"
        )


def connect_prediction_recorder(settings: Settings) -> PostgresPredictionRecorder:
    """Connect to PostgreSQL and verify it before serving traffic."""
    logger.debug("postgres_connection_started")
    recorder = PostgresPredictionRecorder(
        settings.database_url, model_name=settings.model_name, model_alias=settings.model_alias
    )
    recorder.ready()
    logger.info("postgres_connected")
    return recorder
