"""Operational liveness and readiness routes."""

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api.modules.health.schemas import HealthResponse, ReadinessChecks, ReadinessResponse

router = APIRouter(tags=["operations"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report process liveness without checking dependencies."""
    return HealthResponse(status="ok")


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Expose Prometheus metrics to the Alloy scraper."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/ready", response_model=ReadinessResponse)
def ready(request: Request, response: Response) -> ReadinessResponse:
    """Report whether the startup-loaded model and the database connection are available."""
    model_status = "ok" if request.app.state.model is not None else "error"
    database_status = _database_status(request)
    checks = ReadinessChecks(model=model_status, database=database_status)

    if model_status == "ok" and database_status == "ok":
        return ReadinessResponse(status="ready", checks=checks)

    logger.bind(model=model_status, database=database_status).warning("readiness_check_degraded")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="degraded", checks=checks)


def _database_status(request: Request) -> Literal["ok", "error"]:
    """Actively verify the database connection; a stale check would hide an outage."""
    recorder = request.app.state.prediction_recorder
    if recorder is None:
        return "error"
    try:
        recorder.ready()
    except Exception:
        return "error"
    return "ok"
