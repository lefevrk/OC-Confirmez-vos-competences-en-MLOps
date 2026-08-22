"""FastAPI lifespan composition root."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from loguru import logger

from api.infra.config import get_settings
from api.infra.logging import configure_logging
from api.infra.metrics import MLFLOW_ERRORS, MODEL_INFO, POSTGRES_ERRORS
from api.infra.mlflow_model import load_champion
from api.infra.postgres.tracking import connect_prediction_recorder


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load all external serving dependencies before accepting traffic."""
    configure_logging()
    app.state.settings = None
    app.state.model = None
    app.state.prediction_recorder = None
    app.state.startup_error = None

    try:
        app.state.settings = get_settings()
    except Exception as exc:
        app.state.startup_error = str(exc)
        logger.bind(error=str(exc)).error("startup_settings_invalid")
    else:
        configure_logging(level=app.state.settings.log_level)
        try:
            app.state.model = load_champion(app.state.settings)
        except Exception as exc:
            MLFLOW_ERRORS.inc()
            app.state.startup_error = str(exc)
            logger.bind(error=str(exc)).error("startup_model_load_failed")
        else:
            MODEL_INFO.labels(
                model_version=app.state.model.version,
                model_alias=app.state.settings.model_alias,
            ).set(1)

        try:
            app.state.prediction_recorder = connect_prediction_recorder(app.state.settings)
        except Exception as exc:
            POSTGRES_ERRORS.inc()
            app.state.startup_error = str(exc)
            logger.bind(error=str(exc)).error("startup_postgres_connection_failed")

    yield
