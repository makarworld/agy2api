import logging
import os
import re
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_api_key

logger = logging.getLogger(__name__)

router = APIRouter()

CONFIG_KEYS = [
    # Boolean flags
    "AGY_POOL_ENABLED",
    "AGY_THOUGHT_AS_TEXT",
    "AGY_HTTP_TRIM_TOOL_RESULTS",
    "AGY_HTTP_EMPTY_AS_EMPTY_CONTENT",
    "AGY_AUTO_CLASSIFIER_SHORTCUT",
    "AGY_OAUTH_REFRESH_ENABLED",
    "AGY_SSL_VERIFY",
    "AGY_POOL_GIT_AUTOSYNC",
    "AGY_HTTP_DEBUG",
    # String / numeric values
    "AGY_TRANSPORT",
    "AGY_FORCE_MODEL",
    "AGY_GOOGLE_PROXY",
    "AGY_POOL_COOLDOWN_SECONDS",
    "AGY_POOL_MAX_RETRIES",
    "AGY_WARM_IDLE_TIMEOUT_SECONDS",
    "AGY_WARM_MAX_SESSIONS",
    "AGY_OAUTH_REFRESH_SKEW_SECONDS",
]

BOOLEAN_KEYS = {
    "AGY_POOL_ENABLED",
    "AGY_THOUGHT_AS_TEXT",
    "AGY_HTTP_TRIM_TOOL_RESULTS",
    "AGY_HTTP_EMPTY_AS_EMPTY_CONTENT",
    "AGY_AUTO_CLASSIFIER_SHORTCUT",
    "AGY_OAUTH_REFRESH_ENABLED",
    "AGY_SSL_VERIFY",
    "AGY_POOL_GIT_AUTOSYNC",
    "AGY_HTTP_DEBUG",
}


def _env_path() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


def _read_env_file() -> Dict[str, str]:
    path = _env_path()
    env_vars = {}
    if not os.path.exists(path):
        return env_vars
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars


def _update_env_file(updates: Dict[str, str]) -> None:
    path = _env_path()
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                updated_keys.add(k)
                continue
        new_lines.append(line)

    # Append any remaining keys that weren't in the file
    for k, v in updates.items():
        if k not in updated_keys:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{k}={v}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]


@router.get("/settings", summary="Get runtime environment settings")
async def get_settings(api_key: str = Depends(get_api_key)):
    file_vars = _read_env_file()
    result = {}
    for k in CONFIG_KEYS:
        val = os.environ.get(k, file_vars.get(k, ""))
        if k in BOOLEAN_KEYS:
            result[k] = str(val).strip().lower() in ("true", "1", "yes")
        else:
            result[k] = str(val)
    return {"settings": result}


@router.put("/settings", summary="Update runtime environment settings")
async def update_settings(req: SettingsUpdateRequest, api_key: str = Depends(get_api_key)):
    updates_str: Dict[str, str] = {}
    for k, v in req.settings.items():
        if k not in CONFIG_KEYS:
            continue
        if k in BOOLEAN_KEYS:
            str_val = "true" if bool(v) else "false"
        else:
            str_val = str(v).strip() if v is not None else ""

        os.environ[k] = str_val
        updates_str[k] = str_val

    try:
        _update_env_file(updates_str)
    except Exception as e:
        logger.error(f"Failed to update .env file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to persist .env file: {e}")

    return {"status": "ok", "updated": list(updates_str.keys())}
