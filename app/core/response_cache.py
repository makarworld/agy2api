import hashlib
import json
import time
from typing import Any, List, Optional

_CACHE: dict[str, tuple[Any, float]] = {}
_CACHE_MAX_SIZE = 256
_CACHE_TTL = 600.0  # 10 minutes


def get_cached_response(model: str, messages: List[dict], temperature: Optional[float] = None) -> Optional[Any]:
    if temperature is not None and temperature > 0:
        return None

    cache_key = _make_key(model, messages)
    entry = _CACHE.get(cache_key)
    if not entry:
        return None

    data, expire_at = entry
    if time.time() > expire_at:
        _CACHE.pop(cache_key, None)
        return None
    return data


def put_cached_response(model: str, messages: List[dict], response: Any, temperature: Optional[float] = None) -> None:
    if temperature is not None and temperature > 0:
        return

    if len(_CACHE) >= _CACHE_MAX_SIZE:
        oldest_key = min(_CACHE.keys(), key=lambda k: _CACHE[k][1])
        _CACHE.pop(oldest_key, None)

    cache_key = _make_key(model, messages)
    _CACHE[cache_key] = (response, time.time() + _CACHE_TTL)


def _make_key(model: str, messages: List[dict]) -> str:
    raw = json.dumps({"m": model, "msg": messages}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
