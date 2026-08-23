"""Bearer-token authentication, shared across presentation modules."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.infra.config import get_settings

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
