"""Token-based authentication for GET /evidently — the only route still gated.

`/predictions` and `/` (the Gradio demo) are intentionally left open (see
docs/design/security.md) so the API and demo are reachable without setup.
Basic is used here rather than Bearer because it's meant to be opened
directly in a browser — browsers only prompt their native login popup for
Basic Auth, not for an arbitrary Bearer header.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from api.common.config import get_settings

basic_security = HTTPBasic(auto_error=False)


def verify_basic_auth(
    credentials: HTTPBasicCredentials | None = Depends(basic_security),
) -> str:
    """Verify API_TOKEN as an HTTP Basic password. Returns 401 if missing or invalid.

    The username is not checked — API_TOKEN is a single shared secret, not a
    per-user credential; any username works. The WWW-Authenticate header is
    set on every 401 so the browser's native login prompt appears (it
    wouldn't if this were silently a 401 with no such header).

    If API_TOKEN is not set (empty), authentication is disabled — handy for
    local development.
    """
    api_token = get_settings().api_token
    if not api_token:
        return ""
    if credentials is None or credentials.password != api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.password
