"""HTTP presentation layer for scoring."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger

from api.infra.observability.metrics import (
    INFERENCE_LATENCY,
    POSTGRES_ERRORS,
    PREDICTION_DECISIONS,
    PREDICTION_SCORE,
)
from api.modules.scoring.ports.model import ScoringModel
from api.modules.scoring.ports.prediction_recorder import PredictionRecorder
from api.modules.scoring.presentation.schemas import PredictionRequest, PredictionResponse
from api.modules.scoring.services.predict import predict

router = APIRouter(prefix="/predictions", tags=["scoring"])


def get_model(request: Request) -> ScoringModel:
    """Return the model loaded at startup. Returns 503 if it never loaded."""
    model = request.app.state.model
    if model is None:
        logger.warning("prediction_rejected_model_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="model unavailable"
        )
    return model


def get_recorder(request: Request) -> PredictionRecorder:
    """Return the prediction recorder connected at startup. Returns 503 if unavailable."""
    recorder = request.app.state.prediction_recorder
    if recorder is None:
        POSTGRES_ERRORS.inc()
        logger.warning("prediction_rejected_recorder_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="storage unavailable"
        )
    return recorder


@router.post(
    "",
    response_model=PredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="Scorer un dossier client",
    response_description="Score calculé et décision associée",
    responses={
        422: {
            "description": "Payload invalide — champ manquant, hors borne, type incorrect, "
            'ou champ inconnu (`extra="forbid"`)'
        },
        500: {
            "description": "Erreur inattendue du modèle, ou probabilité renvoyée hors de "
            "l'intervalle [0, 1] (`InvalidProbabilityError`)"
        },
        503: {"description": "Modèle ou base de données indisponibles (échec au démarrage)"},
    },
)
def create_prediction(
    payload: PredictionRequest,
    model: ScoringModel = Depends(get_model),
    recorder: PredictionRecorder = Depends(get_recorder),
) -> PredictionResponse:
    """Calcule un score de crédit et une décision à partir des 50 features du dossier.

    Le modèle et la connexion base de données sont ceux chargés une seule
    fois au démarrage de l'application, jamais rechargés à la volée. Chaque
    appel réussi persiste l'événement dans PostgreSQL et alimente les
    métriques Prometheus dédiées au scoring (score, décision, latence
    d'inférence). Aucune authentification requise — voir la page Sécurité
    de la documentation pour le compromis assumé.
    """
    result = predict(model, recorder, payload.model_features())

    INFERENCE_LATENCY.observe(result.inference_latency_ms / 1_000)
    PREDICTION_SCORE.observe(result.probability)
    PREDICTION_DECISIONS.labels(decision="refused" if result.decision else "accepted").inc()

    return PredictionResponse(
        prediction_id=result.prediction_id,
        probability=result.probability,
        decision=result.decision,
        model_version=result.model_version,
    )
