"""FastAPI application entry point."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from api.bootstrap import lifespan
from api.common.error_handling import BaseModuleErrorHandler
from api.infra.observability_middleware import ObservabilityMiddleware
from api.modules.health.router import router as health_router
from api.modules.scoring.presentation.error_handler import ScoringErrorHandler  # noqa: F401
from api.modules.scoring.presentation.router import router as scoring_router

app = FastAPI(title="Credit scoring API", lifespan=lifespan)
app.add_middleware(ObservabilityMiddleware)
app.include_router(health_router)
app.include_router(scoring_router)

BaseModuleErrorHandler.register_all(app)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Log the rejected field names, never the submitted values, and return 422."""
    fields = [".".join(str(part) for part in error["loc"][1:]) for error in exc.errors()]
    logger.bind(fields=fields).warning("request_validation_rejected")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures instead of letting them vanish, and return a bare 500."""
    logger.exception("unhandled_exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "internal server error"},
    )
