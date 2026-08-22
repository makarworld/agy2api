import os
from fastapi import Security, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

from dotenv import load_dotenv
load_dotenv()

# Default to "sk-dummy" if not set, for local testing without strict enforcement
API_KEY = os.environ.get("AGY_API_KEY", "sk-dummy")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_COMPAT_API_KEY", API_KEY)

def get_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def get_anthropic_api_key(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    """
    Anthropic clients send the key via `x-api-key`. Some OAuth-style
    clients send `Authorization: Bearer <token>` instead — accept both.
    """
    provided = x_api_key
    if not provided and authorization:
        parts = authorization.split(" ", 1)
        provided = parts[1] if len(parts) == 2 else authorization

    if not provided or provided != ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return provided
