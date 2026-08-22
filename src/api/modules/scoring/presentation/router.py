"""HTTP presentation layer for scoring."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from api.infra.config import get_settings
from api.infra.metrics import (
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
security = HTTPBearer(auto_error=False)


def verify_token(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
    """Verify the Bearer token. Returns 401 if missing or invalid.

    If API_TOKEN is not set (empty), authentication is disabled — handy for
    local development.
    """
    api_token = get_settings().api_token
    if not api_token:
        return ""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing token, use Authorization: Bearer <token>",
        )
    if credentials.credentials != api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return credentials.credentials


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
    dependencies=[Depends(verify_token)],
)
def create_prediction(
    payload: PredictionRequest,
    model: ScoringModel = Depends(get_model),
    recorder: PredictionRecorder = Depends(get_recorder),
) -> PredictionResponse:
    """Score validated input with the model loaded during application startup."""
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
