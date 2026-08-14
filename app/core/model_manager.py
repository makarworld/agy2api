import asyncio
import logging
import time
from typing import List
from app.api.models import Model

logger = logging.getLogger(__name__)

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
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        logger.error("Timeout fetching models from `agy models` CLI")
        return []

    if proc.returncode != 0:
        err = stderr.decode().strip()
        logger.error(f"`agy models` failed with return code {proc.returncode}: {err}")
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
    Returns available AI models with in-memory caching.
    Refreshes automatically when TTL expires.
    """
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
