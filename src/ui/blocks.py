"""Gradio user interface consuming the public scoring HTTP API.

The UI deliberately does not import the scoring use case or its runtime
dependencies.  Submissions are sent to ``POST /predictions`` so the API is
the single validation and execution boundary for every client.
"""

from pathlib import Path
from typing import Any, Literal, get_args, get_origin

import gradio as gr
import httpx
import pandas as pd

from api.modules.scoring.presentation.schemas import PredictionRequest

SAMPLES_PATH = Path(__file__).parent / "sample_data" / "demo_samples.csv"
_SAMPLES = pd.read_csv(SAMPLES_PATH)

_FIELD_NAMES = list(PredictionRequest.model_fields.keys())
_ALIASES = [field.alias or name for name, field in PredictionRequest.model_fields.items()]


class PredictionApiClient:
    """Small HTTP client for the API contract consumed by the UI."""

    def __init__(self, base_url: str, token: str, timeout_seconds: float = 15.0) -> None:
        """Configure the scoring API endpoint and its optional Bearer token."""
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds

    def predict(self, values: list[Any]) -> dict[str, Any]:
        """Submit raw form values and return the API's JSON response."""
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        payload = dict(zip(_ALIASES, values, strict=True))
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/predictions", json=payload, headers=headers
                )
        except httpx.RequestError as exc:
            raise gr.Error(
                "Le service de prédiction est injoignable, réessayez plus tard."
            ) from exc

        if response.status_code == 422:
            raise gr.Error(_format_validation_error(response.json()))
        if response.status_code == 401:
            raise gr.Error("La démo ne peut pas s'authentifier auprès de l'API.")
        if response.status_code == 503:
            raise gr.Error("Le service de prédiction est indisponible, réessayez plus tard.")
        if response.is_error:
            raise gr.Error("La prédiction a échoué, réessayez plus tard.")
        return response.json()


def _literal_choices(annotation: Any) -> list[str] | None:
    """Return a field's fixed choices if it's a Literal type, else None."""
    if get_origin(annotation) is Literal:
        return list(get_args(annotation))
    return None


def _build_input(name: str, alias: str) -> gr.Component:
    """Map a published request field to the matching Gradio component."""
    choices = _literal_choices(PredictionRequest.model_fields[name].annotation)
    if choices is not None:
        return gr.Dropdown(choices=choices, label=alias, render=False)
    return gr.Number(label=alias, render=False)


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    """Split a list into fixed-size chunks, laid out as form rows."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def sample_row() -> list[Any]:
    """Pick a random real example and return its values in field order."""
    row = _SAMPLES.sample(n=1).iloc[0]
    return [row[alias] if pd.notna(row[alias]) else None for alias in _ALIASES]


def predict_row(client: PredictionApiClient, *values: Any) -> str:
    """Submit the form to the API and render its successful response."""
    result = client.predict(list(values))
    decision = "Refusé" if result["decision"] else "Accepté"
    return (
        f"**Score du modèle : {result['probability']:.3f}**\n\n"
        f"Décision : **{decision}**  \n"
        f"Version du modèle : `{result['model_version']}`\n\n"
        "*Ce score n'est pas une probabilité calibrée : le modèle est un "
        "classifieur binaire géré pour le déséquilibre des classes — le "
        "score ne fait que positionner la prédiction par rapport au seuil "
        "de décision, il ne s'interprète pas comme une chance réelle de "
        "défaut.*"
    )


def _format_validation_error(body: dict[str, Any]) -> str:
    """Turn FastAPI's 422 body into concise, per-field UI feedback."""
    details = body.get("detail", [])
    lines = [
        f"- **{'.'.join(str(part) for part in error.get('loc', [])[1:])}** : "
        f"{error.get('msg', 'valeur invalide')}"
        for error in details
        if isinstance(error, dict)
    ]
    return "Entrée invalide :\n" + "\n".join(lines or ["valeur invalide"])


def build_demo_blocks(client: PredictionApiClient) -> gr.Blocks:
    """Build the demo UI around the external API client."""
    with gr.Blocks(title="Credit Scoring — démo") as demo:
        gr.Markdown(
            "# Crédit scoring — démo\n"
            "Charge un exemple réel, ajuste les champs si besoin, puis prédit."
        )
        sample_button = gr.Button("Charger un nouvel exemple")
        inputs = [
            _build_input(name, alias) for name, alias in zip(_FIELD_NAMES, _ALIASES, strict=True)
        ]
        for row_fields in _chunked(inputs, 5):
            with gr.Row():
                for field in row_fields:
                    field.render()
        predict_button = gr.Button("Prédire", variant="primary")
        output = gr.Markdown()
        sample_button.click(sample_row, inputs=None, outputs=inputs)
        predict_button.click(
            lambda *values: predict_row(client, *values), inputs=inputs, outputs=output
        )
        demo.load(sample_row, inputs=None, outputs=inputs)
    return demo
