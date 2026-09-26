import logging
import json
import os
import re
import sys
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
    "AGY_THOUGHT_TEXT_PREFIX",
    "AGY_THOUGHT_TEXT_SUFFIX",
    "AGY_HTTP_TRIM_TOOL_RESULTS",
    "AGY_HTTP_EMPTY_AS_EMPTY_CONTENT",
    "AGY_AUTO_CLASSIFIER_MODEL",
    "AGY_AUTO_CLASSIFIER_EFFORT",
    "AGY_AUTO_CLASSIFIER_SHORTCUT",
    "AGY_OAUTH_REFRESH_ENABLED",
    "AGY_SSL_VERIFY",
    "AGY_HTTP_DEBUG",
    "AGY_POOL_GIT_AUTOSYNC",
    # String / numeric values
    "AGY_TRANSPORT",
    "AGY_FORCE_MODEL",
    "AGY_GOOGLE_PROXY",
    "AGY_POOL_COOLDOWN_SECONDS",
    "AGY_POOL_MAX_RETRIES",
    "AGY_WARM_IDLE_TIMEOUT_SECONDS",
    "AGY_WARM_MAX_SESSIONS",
    "AGY_OAUTH_REFRESH_SKEW_SECONDS",
    "AGY_MODEL_ALIASES",
    "AGY_HTTP_MAX_OUTPUT_TOKENS",
    "AGY_HTTP_MAX_TOOL_RESULT_CHARS",
    "AGY_HTTP_OLD_TOOL_RESULT_CHARS",
    "AGY_HTTP_RETRY_TOOL_RESULT_CHARS",
    "AGY_POOL_GIT_AUTOSYNC_INTERVAL_SECONDS",
]

BOOLEAN_KEYS = {
    "AGY_POOL_ENABLED",
    "AGY_THOUGHT_AS_TEXT",
    "AGY_HTTP_TRIM_TOOL_RESULTS",
    "AGY_HTTP_EMPTY_AS_EMPTY_CONTENT",
    "AGY_AUTO_CLASSIFIER_SHORTCUT",
    "AGY_OAUTH_REFRESH_ENABLED",
    "AGY_SSL_VERIFY",
    "AGY_HTTP_DEBUG",
    "AGY_POOL_GIT_AUTOSYNC",
}


def _env_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), ".env")
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


_last_env_mtime: float = 0.0
_last_loaded_keys: set[str] = set()

try:
    _p = _env_path()
    if os.path.exists(_p):
        _last_env_mtime = os.path.getmtime(_p)
except OSError:
    pass


def reload_env_if_modified(force: bool = False) -> bool:
    """Reload environment variables from .env if the file has been modified on disk."""
    global _last_env_mtime, _last_loaded_keys
    path = _env_path()
    if not os.path.exists(path):
        return False
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return False

    if not force and mtime == _last_env_mtime:
        return False

    try:
        from dotenv import dotenv_values

        vals = dotenv_values(path)
        for k, v in vals.items():
            if v is not None:
                os.environ[k] = str(v)
            elif k in os.environ:
                del os.environ[k]

        current_keys = set(vals.keys())
        if _last_loaded_keys:
            for removed_key in _last_loaded_keys - current_keys:
                if removed_key in os.environ and (removed_key.startswith("AGY_") or removed_key in CONFIG_KEYS):
                    del os.environ[removed_key]

        _last_loaded_keys = current_keys
        _last_env_mtime = mtime
        logger.info(f"[settings] Applied environment changes from .env (mtime={mtime})")
        return True
    except Exception as e:
        logger.warning(f"Failed to reload .env: {e}")
        return False


def _read_env_file() -> Dict[str, str]:
    path = _env_path()
    if not os.path.exists(path):
        return {}
    try:
        from dotenv import dotenv_values

        vals = dotenv_values(path)
        return {k: str(v) for k, v in vals.items() if v is not None}
    except Exception as e:
        logger.warning(f"Failed to read .env via dotenv_values: {e}")
        return {}


def _update_env_file(updates: Dict[str, str]) -> None:
    path = _env_path()
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []
    formatted = {
        key: json.dumps(value, ensure_ascii=False)
        if key in {"AGY_THOUGHT_TEXT_PREFIX", "AGY_THOUGHT_TEXT_SUFFIX"}
        else value
        for key, value in updates.items()
    }
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={formatted[k]}\n")
                updated_keys.add(k)
                continue
        new_lines.append(line)

    # Append any remaining keys that weren't in the file
    for k, v in updates.items():
        if k not in updated_keys:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{k}={formatted[k]}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]


@router.get("/settings", summary="Get runtime environment settings")
async def get_settings(api_key: str = Depends(get_api_key)):
    reload_env_if_modified()
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
        elif k in {"AGY_THOUGHT_TEXT_PREFIX", "AGY_THOUGHT_TEXT_SUFFIX"}:
            str_val = str(v) if v is not None else ""
        else:
            str_val = str(v).strip() if v is not None else ""

        os.environ[k] = str_val
        updates_str[k] = str_val

    try:
        _update_env_file(updates_str)
        path = _env_path()
        if os.path.exists(path):
            global _last_env_mtime
            _last_env_mtime = os.path.getmtime(path)
    except Exception as e:
        logger.error(f"Failed to update .env file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to persist .env file: {e}")

    if "AGY_POOL_ENABLED" in updates_str:
        try:
            from app.core import pool_manager

            await pool_manager.init_pool_state()
        except Exception as e:
            logger.warning(f"Failed to re-sync pool state after settings update: {e}")

    return {"status": "ok", "updated": list(updates_str.keys())}
