import asyncio
import logging
import os
import time
from typing import List, Optional, Tuple
from app.api.models import Model
from app.core import pool_manager

logger = logging.getLogger(__name__)

# Custom names that deliberately don't collide with any client's built-in/native
# model IDs (e.g. Cursor silently routes recognized model names through its own
# subscription instead of hitting the configured custom base URL). Add more
# pairs here as needed.
MODEL_ALIASES = {
    "max-gem": "gemini-3.7-flash-high",
}


def resolve_model_alias(name: str) -> str:
    return MODEL_ALIASES.get(name, name)


def get_force_model() -> Optional[str]:
    """When set (e.g. max-gem), all requests use this model on the backend."""
    value = os.environ.get("AGY_FORCE_MODEL", "").strip()
    return value or None


async def _resolve_requested_model(requested: str) -> str:
    """Maps a client model name to whatever agy CLI actually exposes."""
    if requested in MODEL_ALIASES:
        return MODEL_ALIASES[requested]

    models = await get_available_models()
    ids = [m.id for m in models]

    if requested in ids:
        return requested

    lower = requested.lower()
    for m in ids:
        if m.lower() == lower:
            return m

    if "opus" in lower:
        for m in ids:
            if "opus" in m.lower():
                return m
        return "claude-opus-4-6-thinking"

    if "haiku" in lower:
        for m in ids:
            if "flash" in m.lower() and "low" in m.lower():
                return m
        return "gemini-3.5-flash-low"

    for m in ids:
        if "sonnet" in m.lower():
            return m
    return "claude-sonnet-4-6"


async def resolve_backend_model(requested: str) -> str:
    """Resolve backend model, honoring AGY_FORCE_MODEL when set."""
    force = get_force_model()
    if force:
        return await _resolve_requested_model(force)
    return await _resolve_requested_model(requested)


# Cloud Code Assist HTTP API uses different backend IDs than agy CLI slugs for some models.
_HTTP_MODEL_MAP: dict[str, Tuple[str, Optional[str]]] = {
    "gemini-3.1-pro-high": ("gemini-3.1-pro-low", "high"),
    "gemini-3.1-pro": ("gemini-3.1-pro-low", "low"),
}


def resolve_http_model(name: str) -> Tuple[str, Optional[str]]:
    """Map agy/alias model name to (backend_model, thinking_level) for HTTP transport."""
    resolved = resolve_model_alias(name)
    entry = _HTTP_MODEL_MAP.get(resolved)
    if entry:
        return entry
    return resolved, None


# In-memory cache
_CACHED_MODELS: List[Model] = []
_LAST_FETCH_TIME: float = 0
_CACHE_TTL_SECONDS: int = 3600  # Refresh cache every 1 hour
_LOCK = asyncio.Lock()

# Safe fallback models if agy CLI fails or is unreachable
FALLBACK_MODELS = [
    "gemini-3.7-flash-high",
    "Gemini 3.7 Flash (High)",
    "gemini-3.7-flash-medium",
    "Gemini 3.7 Flash (Medium)",
    "gemini-3.6-flash-high",
    "Gemini 3.6 Flash (High)",
    "gemini-3.1-pro-high",
    "Gemini 3.1 Pro (High)",
    "claude-sonnet-4-6",
    "Claude Sonnet 4.6 (Thinking)",
    "gpt-oss-120b-medium",
    "GPT-OSS 120B (Medium)"
]


async def fetch_models_from_cli() -> List[Model]:
    """
    Executes `agy models` CLI command and parses the output into Model objects.
    Returns both slug IDs and display names for maximum OpenAI client compatibility.
    """
    cmd = ["agy", "models"]
    logger.info("Fetching available models from Antigravity CLI...")

    try:
        if pool_manager.pool_enabled():
            returncode, stdout, stderr = await pool_manager.run_agy_subprocess_without_pool(cmd, timeout=10.0)
        else:
            returncode, stdout, stderr = await pool_manager.execute_agy(cmd, timeout=10.0)
    except asyncio.TimeoutError:
        logger.error("Timeout fetching models from `agy models` CLI")
        return []
    except RuntimeError as e:
        logger.error(f"`agy models` failed: {e}")
        return []

    if returncode != 0:
        err = stderr.decode().strip()
        logger.error(f"`agy models` failed with return code {returncode}: {err}")
        return []

    lines = stdout.decode().strip().splitlines()
    models: List[Model] = []
    seen_ids = set()
    created_ts = int(time.time())

    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        slug_id = parts[0].strip()
        display_name = parts[1].strip() if len(parts) > 1 else slug_id

        # Add slug ID
        if slug_id and slug_id not in seen_ids:
            models.append(Model(id=slug_id, created=created_ts))
            seen_ids.add(slug_id)
            
        # Add display name if different from slug
        if display_name and display_name != slug_id and display_name not in seen_ids:
            models.append(Model(id=display_name, created=created_ts))
            seen_ids.add(display_name)

    logger.info(f"Successfully fetched {len(models)} model IDs/aliases from agy CLI")
    return models


async def get_available_models(force_refresh: bool = False) -> List[Model]:
    """
    Returns available AI models (including custom aliases) with in-memory caching.
    Refreshes automatically when TTL expires.
    """
    models = await _get_available_models_cached(force_refresh)
    existing_ids = {m.id for m in models}
    created_ts = int(time.time())
    alias_models = [Model(id=alias, created=created_ts) for alias in MODEL_ALIASES if alias not in existing_ids]
    return models + alias_models


async def _get_available_models_cached(force_refresh: bool = False) -> List[Model]:
    global _CACHED_MODELS, _LAST_FETCH_TIME

    now = time.time()
    if not force_refresh and _CACHED_MODELS and (now - _LAST_FETCH_TIME < _CACHE_TTL_SECONDS):
        return _CACHED_MODELS

    async with _LOCK:
        # Double check after acquiring lock
        now = time.time()
        if not force_refresh and _CACHED_MODELS and (now - _LAST_FETCH_TIME < _CACHE_TTL_SECONDS):
            return _CACHED_MODELS

        models = await fetch_models_from_cli()
        if models:
            _CACHED_MODELS = models
            _LAST_FETCH_TIME = now
            return _CACHED_MODELS

        # Fallback to existing cache if available
        if _CACHED_MODELS:
            logger.warning("Using stale model cache after fetch failure")
            return _CACHED_MODELS

        # Fallback to static default list
        logger.warning("Using default fallback models")
        created_ts = int(now)
        _CACHED_MODELS = [Model(id=m, created=created_ts) for m in FALLBACK_MODELS]
        _LAST_FETCH_TIME = now
        return _CACHED_MODELS
