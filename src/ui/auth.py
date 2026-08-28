"""Adapts verify_basic_auth's HTTPBasic parsing to Gradio's auth_dependency contract.

Gradio calls `auth_dependency(request)` as a bare, synchronous function call
(see `gradio/routes.py`, `get_current_user`) — never through FastAPI's own
`Depends()` resolution, and never awaited. An `async def` here would return
an unawaited coroutine object instead of a value: always truthy, so every
request would silently pass authentication. `auth_dependency` must stay
synchronous, so `HTTPBasic.__call__`'s parsing (itself plain, non-awaiting
logic despite being declared `async def`) is reproduced by hand instead of
reused.
"""

from base64 import b64decode
import binascii

from fastapi import Request
from fastapi.security import HTTPBasicCredentials
from fastapi.security.utils import get_authorization_scheme_param

from api.infra.auth import verify_basic_auth


def verify_demo_auth(request: Request) -> str:
    """Verify API_TOKEN as an HTTP Basic password, same check as GET /evidently."""
    return verify_basic_auth(_parse_basic_credentials(request))


def _parse_basic_credentials(request: Request) -> HTTPBasicCredentials | None:
    """Mirror HTTPBasic(auto_error=False).__call__, without the async wrapper."""
    authorization = request.headers.get("Authorization")
    scheme, param = get_authorization_scheme_param(authorization)
    if not authorization or scheme.lower() != "basic":
        return None
    try:
        data = b64decode(param).decode("ascii")
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None
    username, separator, password = data.partition(":")
    if not separator:
        return None
    return HTTPBasicCredentials(username=username, password=password)
