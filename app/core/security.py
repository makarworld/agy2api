import os
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

# Default to "sk-dummy" if not set, for local testing without strict enforcement
API_KEY = os.environ.get("AGY_API_KEY", "sk-dummy")

def get_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials
