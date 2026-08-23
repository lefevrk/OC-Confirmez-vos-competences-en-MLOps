"""Shared payload builder for the champion serving schema, used across test suites."""

from annotated_types import Le
from pydantic.fields import FieldInfo

from api.modules.scoring.presentation.schemas import PredictionRequest


def _numeric_default(field: FieldInfo) -> float | int:
    """Pick a value satisfying the field's own type and sign bound, if any."""
    negative = any(isinstance(constraint, Le) for constraint in field.metadata)
    return (-1 if negative else 1) if field.annotation is int else (-1.0 if negative else 1.0)


def valid_payload() -> dict[str, float | int | str]:
    """Build a payload containing every required model feature."""
    categorical_values = {
        "organization_type": "Bank",
        "code_gender": "F",
        "occupation_type": "Accountants",
        "name_family_status": "Married",
        "name_education_type": "Higher education",
    }

    return {
        field_name: categorical_values.get(field_name, _numeric_default(field))
        for field_name, field in PredictionRequest.model_fields.items()
        if field.is_required()
    }
