"""Response schemas for operational endpoints."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness response."""

    status: Literal["ok"] = Field(description='Toujours "ok" — le process a démarré')


class ReadinessChecks(BaseModel):
    """Dependency states used to explain readiness failures."""

    model: Literal["ok", "error"] = Field(description="Modèle de scoring chargé au démarrage")
    database: Literal["ok", "error"] = Field(description="Connexion PostgreSQL/Supabase")


class ReadinessResponse(BaseModel):
    """Readiness response."""

    status: Literal["ready", "degraded"] = Field(
        description='"degraded" si le modèle ou la base (ou les deux) sont indisponibles'
    )
    checks: ReadinessChecks = Field(description="Détail par dépendance")
