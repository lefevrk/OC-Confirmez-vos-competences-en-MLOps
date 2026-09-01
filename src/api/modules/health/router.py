"""Operational liveness and readiness routes."""

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api.modules.health.schemas import HealthResponse, ReadinessChecks, ReadinessResponse

router = APIRouter(tags=["operations"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness",
    response_description="Le process a démarré",
)
def health() -> HealthResponse:
    """Liveness pure : répond dès que le process a démarré, sans vérifier ses dépendances.

    Ne renvoie jamais autre chose que 200 — un process qui répond à cette
    route est par définition vivant. Utiliser `GET /ready` pour savoir si
    le modèle et la base de données sont, eux, réellement disponibles.
    """
    return HealthResponse(status="ok")


@router.get(
    "/metrics",
    summary="Métriques Prometheus",
    response_description="Métriques au format texte Prometheus",
    responses={200: {"content": {CONTENT_TYPE_LATEST: {}}, "description": "Métriques Prometheus"}},
    include_in_schema=False,
)
def metrics() -> Response:
    """Expose les métriques Prometheus définies dans `api.infra.observability.metrics` au format texte.

    Scrapé en continu par Grafana Alloy (`prometheus.scrape`) — débit,
    latence et taux d'erreur HTTP, plus des métriques spécifiques au
    scoring (distribution des scores, taux de décision, latence
    d'inférence isolée, échecs MLflow/PostgreSQL).
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness",
    response_description="Modèle et base de données disponibles",
    responses={
        503: {
            "model": ReadinessResponse,
            "description": "Le modèle ou la base de données (ou les deux) sont indisponibles — "
            "le détail par dépendance est dans `checks`",
        }
    },
)
def ready(request: Request, response: Response) -> ReadinessResponse:
    """Vérifie activement le modèle chargé au démarrage et la connexion PostgreSQL.

    Contrairement à `GET /health`, ce endpoint interroge réellement ses
    dépendances à chaque appel plutôt que de renvoyer un statut mis en
    cache — une base qui vient de tomber est détectée immédiatement.
    """
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
