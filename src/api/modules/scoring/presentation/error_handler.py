"""Maps scoring domain errors to HTTP status codes."""

from fastapi import status

from api.common.error_handling import BaseModuleErrorHandler
from api.modules.scoring.domain.errors import (
    InferenceError,
    InvalidProbabilityError,
    PredictionPersistenceError,
    ScoringError,
)


class ScoringErrorHandler(BaseModuleErrorHandler):
    """FastAPI exception handler that maps scoring domain errors to HTTP status codes."""

    base_exception = ScoringError
    status_map = {
        InferenceError: (status.HTTP_500_INTERNAL_SERVER_ERROR, "prediction failed"),
        InvalidProbabilityError: (status.HTTP_500_INTERNAL_SERVER_ERROR, "prediction failed"),
        PredictionPersistenceError: (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "prediction succeeded but could not be recorded",
        ),
    }
