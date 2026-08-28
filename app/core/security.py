import os

from dotenv import load_dotenv
from fastapi import Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.key_manager import is_master_key, validate_and_consume_key

load_dotenv()

security = HTTPBearer(auto_error=False)

API_KEY = os.environ.get("AGY_API_KEY", "sk-dummy")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_COMPAT_API_KEY", API_KEY)
ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD", os.environ.get("AGY_ADMIN_PASSWORD", API_KEY)
)


def get_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    authorization: str | None = Header(None),
) -> str:
    provided = None
    if credentials and credentials.credentials:
        provided = credentials.credentials
    elif authorization:
        parts = authorization.split(" ", 1)
        provided = parts[1] if len(parts) == 2 else authorization

    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key_info = validate_and_consume_key(provided)
    return key_info.key


def get_anthropic_api_key(
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
) -> str:
    """
    Anthropic clients send the key via `x-api-key`. Some OAuth-style
    clients send `Authorization: Bearer <token>` instead — accept both.
    """
    provided = x_api_key
    if not provided and authorization:
        parts = authorization.split(" ", 1)
        provided = parts[1] if len(parts) == 2 else authorization

    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required",
        )

    key_info = validate_and_consume_key(provided)
    return key_info.key


def require_master_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
) -> str:
    provided = None
    if credentials and credentials.credentials:
        provided = credentials.credentials
    elif x_api_key:
        provided = x_api_key
    elif authorization:
        parts = authorization.split(" ", 1)
        provided = parts[1] if len(parts) == 2 else authorization

    if not provided or not str(provided).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Master key is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key = str(provided).strip()
    if not is_master_key(key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master key required for this operation",
        )
    return key
