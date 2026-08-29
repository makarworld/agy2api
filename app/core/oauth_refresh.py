import json
import logging
import os
import time
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional, Tuple
from urllib.parse import unquote

import httpx

from app.core.cloudcode_common import QUOTA_PROJECT, QUOTA_SUMMARY_URL, cloudcode_headers
from app.core.proxy_config import httpx_client_kwargs

logger = logging.getLogger(__name__)

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
ANTIGRAVITY_TOKEN_REL = os.path.join("antigravity-cli", "antigravity-oauth-token")
OAUTH_CREDS_REL = "oauth_creds.json"

CredentialKind = Literal["antigravity", "gemini_flat"]

_REFRESH_HEADERS = {
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": "Go-http-client/2.0",
    "accept-encoding": "gzip",
}

_verify_cache: dict[str, float] = {}
_VERIFY_CACHE_TTL_SECONDS = int(os.environ.get("AGY_OAUTH_VERIFY_CACHE_SECONDS", "300"))
_verify_lock = asyncio.Lock()
_refresh_lock = asyncio.Lock()

_active_credential: Optional[Tuple[str, CredentialKind]] = None


def refresh_enabled() -> bool:
    return os.environ.get("AGY_OAUTH_REFRESH_ENABLED", "true").strip().lower() == "true"


def refresh_skew_seconds() -> int:
    return int(os.environ.get("AGY_OAUTH_REFRESH_SKEW_SECONDS", "120"))


def env_access_token() -> Optional[str]:
    """Optional live Bearer override (AGY_ACCESS_TOKEN or AGY_BEARER_TOKEN)."""
    for key in ("AGY_ACCESS_TOKEN", "AGY_BEARER_TOKEN"):
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        if value.lower().startswith("bearer "):
            value = value[7:].strip()
        return value
    return None


def _set_active_credential(path: str, kind: CredentialKind) -> None:
    global _active_credential
    _active_credential = (path, kind)


def clear_active_credential_cache() -> None:
    """Test helper — reset credential file selection cache."""
    global _active_credential
    _active_credential = None


def _token_suffix(token: Optional[str]) -> str:
    if not token:
        return "none"
    token = token.strip()
    return f"...{token[-6:]}" if len(token) >= 6 else "..."


def _access_token_suffix(token: Optional[str]) -> str:
    if not token:
        return "none"
    token = token.strip()
    return token[-20:] if len(token) >= 20 else token


def credential_kind_for_path(path: str) -> CredentialKind:
    if path.replace("\\", "/").endswith(ANTIGRAVITY_TOKEN_REL):
        return "antigravity"
    return "gemini_flat"


def access_token_from_path(path: str) -> Optional[str]:
    data = _read_token_file(path)
    if not data:
        return None
    view = _normalize_token_view(data, credential_kind_for_path(path))
    return view.get("access_token")


def _client_id(_kind: CredentialKind) -> str:
    value = os.environ.get("ANTIGRAVITY_CLIENT_ID", "").strip()
    if not value:
        raise RuntimeError("ANTIGRAVITY_CLIENT_ID is not set (required for OAuth refresh)")
    return value


def _client_secret(_kind: CredentialKind) -> str:
    value = os.environ.get("ANTIGRAVITY_CLIENT_SECRET", "").strip()
    if not value:
        raise RuntimeError("ANTIGRAVITY_CLIENT_SECRET is not set (required for OAuth refresh)")
    return value


def token_file_path(gemini_home: Optional[str] = None) -> str:
    """Legacy helper — returns antigravity path. Prefer discover_credential_file()."""
    home = gemini_home or os.path.expanduser("~/.gemini")
    return os.path.join(home, ANTIGRAVITY_TOKEN_REL)


def discover_credential_candidates(gemini_home: Optional[str] = None) -> list[Tuple[str, CredentialKind]]:
    """All existing credential files under ~/.gemini or pool fallback (antigravity first)."""
    home = gemini_home or os.path.expanduser("~/.gemini")
    candidates: list[Tuple[str, CredentialKind]] = []
    for path, kind in (
        (os.path.join(home, ANTIGRAVITY_TOKEN_REL), "antigravity"),
        (os.path.join(home, OAUTH_CREDS_REL), "gemini_flat"),
    ):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            candidates.append((path, kind))

    if not candidates:
        pool_dir = os.path.expanduser(os.environ.get("AGY_POOL_DIR", "~/.agy2api-pool"))
        manifest_path = os.path.join(pool_dir, "accounts.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                for acc in manifest.get("accounts", []):
                    acc_id = acc.get("id")
                    if not acc_id:
                        continue
                    acc_dir = os.path.join(pool_dir, "accounts", acc_id)
                    for filename, kind in (
                        ("antigravity-oauth-token", "antigravity"),
                        ("oauth_creds.json", "gemini_flat"),
                    ):
                        p = os.path.join(acc_dir, filename)
                        if os.path.exists(p) and os.path.getsize(p) > 0:
                            candidates.append((p, kind))
            except Exception as e:
                logger.warning(f"[oauth] Failed reading pool accounts as credential fallback: {e}")

    return candidates


def discover_credential_file(gemini_home: Optional[str] = None) -> Optional[Tuple[str, CredentialKind]]:
    """Return the active or first existing OAuth credential file under ~/.gemini."""
    if _active_credential:
        return _active_credential

    candidates = discover_credential_candidates(gemini_home)
    if not candidates:
        return None
    return candidates[0]


async def discover_verified_credential_file(
    gemini_home: Optional[str] = None,
    *,
    proxy: Optional[str] = None,
) -> Optional[Tuple[str, CredentialKind]]:
    """Pick credential file whose access_token passes quota verify."""
    candidates = discover_credential_candidates(gemini_home)
    if not candidates:
        return None

    first_path = candidates[0][0]
    for path, kind in candidates:
        token = access_token_from_path(path)
        if not token:
            continue
        if _verify_cache_valid(token) or await verify_access_token(token, proxy=proxy):
            if path != first_path:
                first_token = access_token_from_path(first_path)
                logger.info(
                    "[oauth] using verified credential from %s (suffix %s) — "
                    "first candidate %s failed quota (suffix %s)",
                    os.path.basename(path),
                    _token_suffix(token),
                    os.path.basename(first_path),
                    _token_suffix(first_token),
                )
            _set_active_credential(path, kind)
            return path, kind

    for path, kind in candidates:
        if access_token_from_path(path):
            _set_active_credential(path, kind)
            return path, kind

    path, kind = candidates[0]
    _set_active_credential(path, kind)
    return path, kind


def parse_expiry(expiry_raw: Any) -> float:
    """Parse token expiry (RFC3339 string or ms/seconds epoch) into a unix timestamp."""
    if expiry_raw is None or expiry_raw == "":
        return 0.0
    if isinstance(expiry_raw, (int, float)):
        value = float(expiry_raw)
        if value > 1_000_000_000_000:
            return value / 1000.0
        return value

    s = str(expiry_raw).strip()
    try:
        if "." in s:
            head, tail = s.split(".", 1)
            tz_part = ""
            for i, ch in enumerate(tail):
                if ch in "Z+-":
                    tz_part = tail[i:]
                    tail = tail[:i]
                    break
            tail = tail[:6]
            s = f"{head}.{tail}{tz_part}"
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def _format_expiry_rfc3339(expires_in: int) -> str:
    exp_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return exp_dt.strftime("%Y-%m-%dT%H:%M:%S.000000Z")


def _format_expiry_ms(expires_in: int) -> int:
    return int((time.time() + expires_in) * 1000)


def _normalize_refresh_token(raw: Any) -> Optional[str]:
    """Decode URL-encoded refresh tokens from oauth_creds.json before OAuth POST."""
    if not isinstance(raw, str):
        return None
    token = raw.strip()
    if not token:
        return None
    if "%" in token:
        token = unquote(token)
    return token


def _normalize_token_view(data: dict, kind: CredentialKind) -> dict:
    if kind == "antigravity":
        token_obj = data.get("token") or {}
        expiry_raw = token_obj.get("expiry")
        refresh_token = token_obj.get("refresh_token")
        access_token = token_obj.get("access_token")
    else:
        token_obj = data
        expiry_raw = data.get("expiry_date", data.get("expiry"))
        refresh_token = data.get("refresh_token")
        access_token = data.get("access_token")

    if isinstance(refresh_token, str):
        refresh_token = _normalize_refresh_token(refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expiry_ts": parse_expiry(expiry_raw),
    }


def _needs_refresh_from_view(view: dict) -> bool:
    if not view.get("access_token"):
        return True
    expiry_ts = view.get("expiry_ts") or 0.0
    if expiry_ts <= 0:
        return True
    return time.time() >= expiry_ts - refresh_skew_seconds()


def _read_token_file(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_token_file(path: str, data: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def patch_access_token_to_file(
    access_token: str,
    gemini_home: Optional[str] = None,
    *,
    expires_in: int = 3600,
    path: Optional[str] = None,
    kind: Optional[CredentialKind] = None,
) -> str:
    """Write access_token to disk, preserving refresh_token and other fields."""
    access_token = access_token.strip()
    home = gemini_home or os.path.expanduser("~/.gemini")

    if path is None:
        discovered = discover_credential_file(home)
        if discovered:
            path, kind = discovered
        else:
            path = os.path.join(home, OAUTH_CREDS_REL)
            kind = "gemini_flat"

    file_kind = kind or credential_kind_for_path(path)
    data = _read_token_file(path) or {}

    if file_kind == "antigravity":
        token_obj = data.get("token") or {}
        data.setdefault("auth_method", data.get("auth_method", "consumer"))
        data["token"] = {
            **token_obj,
            "access_token": access_token,
            "token_type": token_obj.get("token_type", "Bearer"),
            "expiry": _format_expiry_rfc3339(expires_in),
        }
        if token_obj.get("refresh_token"):
            data["token"]["refresh_token"] = token_obj["refresh_token"]
    else:
        data["access_token"] = access_token
        data.setdefault("token_type", "Bearer")
        data["expiry_date"] = _format_expiry_ms(expires_in)

    _write_token_file(path, data)
    _set_active_credential(path, file_kind)
    logger.info(
        "[oauth] patched access_token on disk (%s, suffix %s)",
        os.path.basename(path),
        _token_suffix(access_token),
    )
    return path


def _apply_refresh_to_file(
    data: dict,
    kind: CredentialKind,
    *,
    access_token: str,
    refresh_token: str,
    token_type: str,
    expires_in: int,
    scope: Optional[str] = None,
    id_token: Optional[str] = None,
) -> dict:
    if kind == "antigravity":
        token_obj = data.get("token") or {}
        data.setdefault("auth_method", data.get("auth_method", "consumer"))
        data["token"] = {
            **token_obj,
            "access_token": access_token,
            "refresh_token": _normalize_refresh_token(refresh_token) or refresh_token,
            "token_type": token_type,
            "expiry": _format_expiry_rfc3339(expires_in),
        }
    else:
        data["access_token"] = access_token
        data["refresh_token"] = _normalize_refresh_token(refresh_token) or refresh_token
        data["token_type"] = token_type
        data["expiry_date"] = _format_expiry_ms(expires_in)
        if scope:
            data["scope"] = scope
        if id_token:
            data["id_token"] = id_token
    return data


def invalidate_verify_cache(access_token: Optional[str] = None) -> None:
    """Drop cached quota-verify results (all tokens, or one access token)."""
    if access_token:
        token = access_token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        _verify_cache.pop(_access_token_suffix(token), None)
    else:
        _verify_cache.clear()


def _verify_cache_valid(access_token: str) -> bool:
    token = access_token.strip()
    if not token:
        return False
    return _verify_cache.get(_access_token_suffix(token), 0.0) > time.time()


_quota_summary_cache: dict[str, Tuple[float, dict]] = {}
_QUOTA_CACHE_TTL_SECONDS = 300.0  # 5 minutes cache to avoid frequent requests to Google
_quota_fetch_lock = asyncio.Lock()


def clear_quota_summary_cache(access_token: Optional[str] = None) -> None:
    """Drop cached quota summary results (all tokens, or one access token)."""
    if access_token:
        token = access_token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        _quota_summary_cache.pop(_access_token_suffix(token), None)
    else:
        _quota_summary_cache.clear()


def _parse_quota_buckets(payload: dict) -> dict:
    """Parse retrieveUserQuotaSummary response into structured limits for UI/MCP."""
    res = {
        "gemini_5h": None,
        "gemini_weekly": None,
        "claude_5h": None,
        "claude_weekly": None,
        "gemini_5h_reset": None,
        "gemini_weekly_reset": None,
        "claude_5h_reset": None,
        "claude_weekly_reset": None,
    }
    if not isinstance(payload, dict):
        return res

    for group in payload.get("groups", []):
        if not isinstance(group, dict):
            continue
        group_name = (group.get("displayName") or "").lower()
        for bucket in group.get("buckets", []):
            if not isinstance(bucket, dict):
                continue
            bucket_id = (bucket.get("bucketId") or "").lower()
            fraction = bucket.get("remainingFraction")
            reset_time = bucket.get("resetTime")

            # Check gemini vs 3p/claude
            if "gemini" in bucket_id or "gemini" in group_name:
                if "5h" in bucket_id:
                    res["gemini_5h"] = fraction
                    res["gemini_5h_reset"] = reset_time
                elif "weekly" in bucket_id:
                    res["gemini_weekly"] = fraction
                    res["gemini_weekly_reset"] = reset_time
            elif "3p" in bucket_id or "claude" in bucket_id or "claude" in group_name:
                if "5h" in bucket_id:
                    res["claude_5h"] = fraction
                    res["claude_5h_reset"] = reset_time
                elif "weekly" in bucket_id:
                    res["claude_weekly"] = fraction
                    res["claude_weekly_reset"] = reset_time
    return res


async def retrieve_account_quota(
    account_dir: Optional[str] = None,
    *,
    access_token: Optional[str] = None,
    proxy: Optional[str] = None,
    pool_account_id: Optional[str] = None,
    force: bool = False,
) -> dict:
    """Fetch quota for an account or token, auto-refreshing on 401 if needed."""
    target_token = access_token
    cred_path = None
    cred_kind = None

    if account_dir and not target_token:
        discovered = discover_credential_candidates(account_dir)
        if discovered:
            cred_path, cred_kind = discovered[0]
            target_token = access_token_from_path(cred_path)

    if not target_token:
        return _parse_quota_buckets({})

    cache_key = _access_token_suffix(target_token)
    now = time.time()
    if not force and cache_key in _quota_summary_cache:
        exp, cached_data = _quota_summary_cache[cache_key]
        if exp > now:
            return cached_data

    async with _quota_fetch_lock:
        if not force and cache_key in _quota_summary_cache:
            exp, cached_data = _quota_summary_cache[cache_key]
            if exp > time.time():
                return cached_data

        try:
            async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=15.0)) as client:
                response = await client.post(
                    QUOTA_SUMMARY_URL,
                    headers=cloudcode_headers(target_token),
                    json={"project": QUOTA_PROJECT},
                )

            if response.status_code == 200:
                parsed = _parse_quota_buckets(response.json())
                _quota_summary_cache[cache_key] = (time.time() + _QUOTA_CACHE_TTL_SECONDS, parsed)
                _verify_cache[cache_key] = time.time() + _VERIFY_CACHE_TTL_SECONDS
                return parsed

            elif response.status_code == 401:
                invalidate_verify_cache(target_token)
                logger.info(
                    "[oauth] Quota check returned 401 (suffix %s) — attempting OAuth refresh for %s",
                    _token_suffix(target_token),
                    pool_account_id or (os.path.basename(account_dir) if account_dir else "active"),
                )
                # Attempt to refresh token if we have account dir or default home
                refreshed = False
                if account_dir:
                    refreshed = await ensure_fresh_credentials(
                        account_dir, proxy=proxy, pool_account_id=pool_account_id, force=True
                    )
                    if refreshed:
                        new_token = access_token_from_path(cred_path) if cred_path else None
                        if new_token:
                            target_token = new_token
                else:
                    refreshed = await ensure_fresh_credentials(proxy=proxy, pool_account_id=pool_account_id, force=True)
                    if refreshed:
                        target_token = read_access_token()

                if refreshed and target_token:
                    async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=15.0)) as client:
                        r2 = await client.post(
                            QUOTA_SUMMARY_URL,
                            headers=cloudcode_headers(target_token),
                            json={"project": QUOTA_PROJECT},
                        )
                    if r2.status_code == 200:
                        parsed = _parse_quota_buckets(r2.json())
                        new_key = _access_token_suffix(target_token)
                        _quota_summary_cache[new_key] = (time.time() + _QUOTA_CACHE_TTL_SECONDS, parsed)
                        _verify_cache[new_key] = time.time() + _VERIFY_CACHE_TTL_SECONDS
                        return parsed

        except Exception as e:
            logger.debug("[oauth] retrieve_account_quota error for %s: %s", pool_account_id or "account", e)

    return _parse_quota_buckets({})


async def retrieve_user_quota(
    access_token: str,
    *,
    project: Optional[str] = None,
    proxy: Optional[str] = None,
    force: bool = False,
) -> dict:
    """Fetch and parse quota summary (Gemini 5h/7d and Claude 5h/7d) with caching."""
    return await retrieve_account_quota(access_token=access_token, proxy=proxy, force=force)


async def verify_access_token(
    access_token: str,
    *,
    proxy: Optional[str] = None,
    project: Optional[str] = None,
) -> bool:
    """Check whether an access token is accepted by Cloud Code Assist quota API."""
    access_token = access_token.strip()
    if not access_token:
        return False

    cache_key = _access_token_suffix(access_token)
    now = time.time()
    if _verify_cache.get(cache_key, 0.0) > now:
        return True

    async with _verify_lock:
        if _verify_cache.get(cache_key, 0.0) > time.time():
            return True

        quota_project = project or QUOTA_PROJECT
        async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=30.0)) as client:
            response = await client.post(
                QUOTA_SUMMARY_URL,
                headers=cloudcode_headers(access_token),
                json={"project": quota_project},
            )

        ok = response.status_code == 200
        if ok:
            _verify_cache[cache_key] = time.time() + _VERIFY_CACHE_TTL_SECONDS
        elif response.status_code == 401:
            logger.warning(
                "[oauth] quota verify 401 (suffix %s) — disk access_token may differ from agy "
                "in-memory Bearer; copy working token from HTTP Toolkit or run "
                "scripts/patch_access_token.py / set AGY_ACCESS_TOKEN",
                _token_suffix(access_token),
            )
        logger.debug(
            "[oauth] quota verify %s (suffix %s, project=%s)",
            "OK" if ok else f"HTTP {response.status_code}",
            _token_suffix(access_token),
            quota_project,
        )
        return ok


async def _verify_access_token_cached(
    access_token: str,
    *,
    proxy: Optional[str] = None,
    pool_account_id: Optional[str] = None,
) -> bool:
    if _verify_cache_valid(access_token):
        return True

    ok = await verify_access_token(access_token, proxy=proxy)
    if ok:
        logger.info(
            "[oauth] access token quota verify OK (suffix %s, pool_account=%s)",
            _token_suffix(access_token),
            pool_account_id or "none",
        )
    return ok


async def refresh_google_token(
    refresh_token: str,
    *,
    proxy: Optional[str] = None,
    kind: CredentialKind = "antigravity",
) -> dict:
    """Exchange a refresh token for a new access token via Google OAuth."""
    refresh_token = _normalize_refresh_token(refresh_token) or refresh_token.strip()
    async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=30.0)) as client:
        response = await client.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": _client_id(kind),
                "client_secret": _client_secret(kind),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers=_REFRESH_HEADERS,
        )
    if response.status_code != 200:
        raise RuntimeError(f"OAuth refresh failed (HTTP {response.status_code}): {response.text[:500]}")

    payload = response.json()
    expires_in = int(payload.get("expires_in", 3600))
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", refresh_token),
        "token_type": payload.get("token_type", "Bearer"),
        "expires_in": expires_in,
        "scope": payload.get("scope"),
        "id_token": payload.get("id_token"),
    }


async def ensure_fresh_credentials(
    gemini_home: Optional[str] = None,
    *,
    proxy: Optional[str] = None,
    pool_account_id: Optional[str] = None,
    force: bool = False,
) -> bool:
    """Refresh the active OAuth credential file when expired or missing access_token.

    Supports antigravity-oauth-token and oauth_creds.json (shared by gemini-cli/agy).
    Returns True if a refresh or disk patch was performed, False if skipped or not needed.
    """
    if not refresh_enabled():
        return False

    home = gemini_home or os.path.expanduser("~/.gemini")

    override_token = env_access_token()
    if override_token and not force:
        if _verify_cache_valid(override_token) or await verify_access_token(override_token, proxy=proxy):
            patched_path = patch_access_token_to_file(override_token, home)
            logger.info(
                "[oauth] using AGY_ACCESS_TOKEN env override (suffix %s, file=%s, pool_account=%s)",
                _token_suffix(override_token),
                os.path.basename(patched_path),
                pool_account_id or "none",
            )
            if pool_account_id:
                from app.core import pool_manager

                await pool_manager.sync_back_credentials(pool_account_id)
            return True

        logger.warning(
            "[oauth] AGY_ACCESS_TOKEN failed quota verify (suffix %s) — ignoring env override",
            _token_suffix(override_token),
        )

    discovered = await discover_verified_credential_file(home, proxy=proxy)
    if not discovered:
        return False

    path, kind = discovered
    data = _read_token_file(path)
    if not data:
        return False

    view = _normalize_token_view(data, kind)
    access_token = view.get("access_token")
    needs_refresh = force or _needs_refresh_from_view(view)

    if not needs_refresh:
        return False

    refresh_token = view.get("refresh_token")
    if not refresh_token:
        logger.warning("[oauth] credential file has no refresh_token — cannot refresh (%s)", path)
        if access_token:
            raise RuntimeError(
                f"No refresh_token in {path} and quota verify failed for access token "
                f"(suffix {_token_suffix(access_token)}) — agy HTTP Toolkit Bearer may end "
                "differently; run scripts/patch_access_token.py or set AGY_ACCESS_TOKEN"
            )
        return False

    async with _refresh_lock:
        data = _read_token_file(path)
        if not data:
            return False
        view = _normalize_token_view(data, kind)
        access_token = view.get("access_token")

        if not force and not _needs_refresh_from_view(view):
            if access_token and (
                _verify_cache_valid(access_token)
                or await _verify_access_token_cached(access_token, proxy=proxy, pool_account_id=pool_account_id)
            ):
                return False

        refresh_token = view.get("refresh_token")
        if not refresh_token:
            logger.warning("[oauth] credential file has no refresh_token — cannot refresh (%s)", path)
            if access_token:
                raise RuntimeError(
                    f"No refresh_token in {path} and quota verify failed for access token "
                    f"(suffix {_token_suffix(access_token)})"
                )
            return False

        client_id = _client_id(kind)
        logger.info(
            "[oauth] Refreshing access token (%s, kind=%s, refresh_suffix=%s, access_suffix=%s, client_id=%s...%s, pool_account=%s, force=%s)",
            os.path.basename(path),
            kind,
            _token_suffix(refresh_token),
            _token_suffix(access_token),
            client_id[:20],
            client_id[-10:],
            pool_account_id or "none",
            force,
        )
        try:
            new_token = await refresh_google_token(refresh_token, proxy=proxy, kind=kind)
        except (RuntimeError, Exception) as e:
            if access_token and await verify_access_token(access_token, proxy=proxy):
                logger.warning(
                    "[oauth] refresh failed but quota verify OK — using existing access token (%s, access_suffix=%s, pool_account=%s): %s",
                    os.path.basename(path),
                    _token_suffix(access_token),
                    pool_account_id or "none",
                    e,
                )
                return False

            hint = (
                "refresh_token on disk may be stale or revoked — disk access_suffix=%s may differ "
                "from agy in-memory Bearer; copy working token from HTTP Toolkit, run "
                "scripts/patch_access_token.py, or set AGY_ACCESS_TOKEN, then re-snapshot the pool "
                "account (POST /v1/accounts or scripts/add_account_to_pool.py)"
            )
            logger.warning(
                "[oauth] refresh failed for %s (kind=%s, refresh_suffix=%s, access_suffix=%s, pool_account=%s, proxy=%s): %s. %s",
                path,
                kind,
                _token_suffix(refresh_token),
                _token_suffix(access_token),
                pool_account_id or "none",
                "yes" if proxy else "no",
                e,
                hint % _token_suffix(access_token),
            )
            raise

        updated = _apply_refresh_to_file(
            data,
            kind,
            access_token=new_token["access_token"],
            refresh_token=new_token["refresh_token"],
            token_type=new_token["token_type"],
            expires_in=new_token["expires_in"],
            scope=new_token.get("scope"),
            id_token=new_token.get("id_token"),
        )
        _write_token_file(path, updated)
        _set_active_credential(path, kind)
        invalidate_verify_cache(access_token)
        logger.info("[oauth] access token refreshed and saved to %s", path)
        if pool_account_id:
            from app.core import pool_manager

            await pool_manager.sync_back_credentials(pool_account_id)
        return True


async def ensure_fresh_antigravity_token(
    gemini_home: Optional[str] = None,
    *,
    proxy: Optional[str] = None,
    pool_account_id: Optional[str] = None,
    force: bool = False,
) -> bool:
    """Alias for ensure_fresh_credentials (pool_manager compatibility)."""
    return await ensure_fresh_credentials(gemini_home, proxy=proxy, pool_account_id=pool_account_id, force=force)


def read_access_token(gemini_home: Optional[str] = None) -> str:
    """Read the current access_token (env override, then active/verified credential file)."""
    override = env_access_token()
    if override:
        return override

    discovered = discover_credential_file(gemini_home)
    if not discovered:
        raise RuntimeError(
            "No OAuth credential file found under ~/.gemini "
            "(expected oauth_creds.json or antigravity-cli/antigravity-oauth-token) — run `agy` to authenticate"
        )

    path, kind = discovered
    data = _read_token_file(path)
    if not data:
        raise RuntimeError(f"OAuth credential file is empty or unreadable: {path}")

    view = _normalize_token_view(data, kind)
    token = view.get("access_token")
    if not token:
        raise RuntimeError(f"No access_token in {path}")
    return token
