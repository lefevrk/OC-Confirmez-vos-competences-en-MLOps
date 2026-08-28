"""Functional tests against a real, already-deployed instance.

Not part of the default test run (excluded from testpaths) — invoked
explicitly in CI after a release/* deployment, against the live URL.
Requires API_BASE_URL in the environment.
"""

from collections.abc import Iterator
import os

import httpx
import pytest
from tests.payloads import valid_payload


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} must be set to run the functional suite against a live deployment")
    return value


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    """An HTTP client bound to the deployed instance under test."""
    base_url = _required_env("API_BASE_URL")
    with httpx.Client(base_url=base_url, timeout=30) as client:
        yield client


def test_prediction_succeeds_with_a_valid_payload(client: httpx.Client) -> None:
    """A real prediction request against the live deployment returns a decision."""
    response = client.post("/predictions", json=valid_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["prediction_id"]
    assert 0 <= body["probability"] <= 1
    assert body["decision"] in (0, 1)
    assert body["model_version"]


def test_prediction_rejects_a_malformed_payload(client: httpx.Client) -> None:
    """A payload missing a required field is rejected before scoring runs."""
    payload = valid_payload()
    del payload["amt_credit"]
    response = client.post("/predictions", json=payload)
    assert response.status_code == 422
