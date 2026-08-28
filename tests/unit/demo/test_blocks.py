"""Unit tests for the Gradio UI's HTTP client and form callbacks."""

import gradio as gr
import httpx
import pytest

from ui.blocks import _ALIASES, PredictionApiClient, predict_row, sample_row


class FakeHttpClient:
    """Context-managed httpx client returning a predetermined response."""

    def __init__(self, response: httpx.Response) -> None:
        """Store the response and captured request arguments."""
        self.response = response
        self.url: str | None = None
        self.json: dict | None = None
        self.headers: dict | None = None

    def __enter__(self) -> "FakeHttpClient":
        """Return the fake client."""
        return self

    def __exit__(self, *_args: object) -> None:
        """Implement the context manager protocol."""

    def post(self, url: str, *, json: dict, headers: dict) -> httpx.Response:
        """Capture a prediction request."""
        self.url, self.json, self.headers = url, json, headers
        return self.response


def test_sample_row_returns_one_value_per_prediction_request_field() -> None:
    """The sampled row aligns 1:1 with the form's field order."""
    values = sample_row()

    assert len(values) == len(_ALIASES)


def test_predict_row_calls_the_public_api_with_the_form_values(monkeypatch) -> None:
    """The UI delegates validation and scoring to POST /predictions."""
    values = sample_row()
    fake_http = FakeHttpClient(
        httpx.Response(200, json={"probability": 0.8, "decision": 1, "model_version": "3"})
    )
    monkeypatch.setattr("ui.blocks.httpx.Client", lambda **_kwargs: fake_http)

    result = predict_row(PredictionApiClient("https://api.example.com", "token"), *values)

    assert "Score du modèle" in result
    assert "Refusé" in result
    assert fake_http.url == "https://api.example.com/predictions"
    assert fake_http.json == dict(zip(_ALIASES, values, strict=True))
    assert fake_http.headers == {"Authorization": "Bearer token"}


def test_predict_row_reports_the_accepted_decision(monkeypatch) -> None:
    """A probability under the model's threshold decides for the positive class."""
    values = sample_row()

    fake_http = FakeHttpClient(
        httpx.Response(200, json={"probability": 0.1, "decision": 0, "model_version": "3"})
    )
    monkeypatch.setattr("ui.blocks.httpx.Client", lambda **_kwargs: fake_http)
    result = predict_row(PredictionApiClient("https://api.example.com", ""), *values)

    assert "Accepté" in result


def test_predict_row_surfaces_api_validation_errors(monkeypatch) -> None:
    """The API's automatic 422 validation becomes readable UI feedback."""
    values = sample_row()
    fake_http = FakeHttpClient(
        httpx.Response(
            422,
            json={
                "detail": [{"loc": ["body", "AMT_CREDIT"], "msg": "Input should be greater than 0"}]
            },
        )
    )
    monkeypatch.setattr("ui.blocks.httpx.Client", lambda **_kwargs: fake_http)

    with pytest.raises(gr.Error) as exc_info:
        predict_row(PredictionApiClient("https://api.example.com", ""), *values)

    message = str(exc_info.value)
    assert "AMT_CREDIT" in message
