import asyncio
import base64
import hashlib
import json
import logging
import os
import platform
import re
import secrets
import shutil
import subprocess
import time
import urllib.parse
import uuid
from typing import Dict, List, Optional, Set, Tuple

import httpx

from app.core import oauth_refresh
from app.core import stats_store
from app.core.proxy_config import get_google_proxy, httpx_client_kwargs

logger = logging.getLogger(__name__)

# Identity files that make up one "account" snapshot. All 5 are swapped by
# default (safe-but-broad default) -- whether installation_id actually gates
# quota separately from oauth_creds.json/google_accounts.json is unverified;
# see plan checklist item (a). Missing files in a snapshot are skipped
# gracefully (not every agy install may populate all three installation_id
# locations).
CREDENTIAL_FILES: List[Tuple[str, str]] = [
    ("antigravity-oauth-token", "antigravity-cli/antigravity-oauth-token"),
    ("oauth_creds.json", "oauth_creds.json"),
    ("google_accounts.json", "google_accounts.json"),
    ("installation_id", "installation_id"),
    ("antigravity-cli_installation_id", "antigravity-cli/installation_id"),
    ("antigravity_installation_id", "antigravity/installation_id"),
]

# Placeholder substrings to detect a rate-limit/quota-exceeded failure from
# agy CLI's combined stderr+stdout. NOT verified against a real quota-exceeded
# response yet (see plan checklist item (b)) -- adjust once observed live.
RATE_LIMIT_SIGNALS: List[str] = [
    "429",
    "resource_exhausted",
    "quota exceeded",
    "rate limit",
    "too many requests",
]

_LOCK = asyncio.Lock()
_active_account_id: Optional[str] = None
_MODEL_COOLDOWNS: Dict[str, Dict[str, float]] = {}
_SESSION_AFFINITY: Dict[str, Tuple[str, float]] = {}
_AFFINITY_TTL = 300.0  # 5 minutes


def pool_enabled() -> bool:
    return os.environ.get("AGY_POOL_ENABLED", "false").strip().lower() == "true"


def _pool_dir() -> str:
    return os.path.expanduser(os.environ.get("AGY_POOL_DIR", "~/.agy2api-pool"))


def _gemini_home() -> str:
    return os.path.expanduser("~/.gemini")


def _read_live_access_token(gemini_home: str) -> Optional[str]:
    try:
        return oauth_refresh.read_access_token(gemini_home)
    except RuntimeError:
        return None


def _read_snapshot_access_token(account_dir: str) -> Optional[str]:
    for src_name in ("antigravity-oauth-token", "oauth_creds.json"):
        token = oauth_refresh.access_token_from_path(os.path.join(account_dir, src_name))
        if token:
            return token
    return None


async def ensure_oauth_fresh_live() -> None:
    await _ensure_oauth_fresh(proxy=get_active_account_proxy())


async def run_agy_subprocess_without_pool(
    cmd: List[str], timeout: Optional[float] = None, input_data: Optional[bytes] = None
) -> Tuple[int, bytes, bytes]:
    """Run agy CLI against live ~/.gemini without pool account rotation."""
    proxy = get_active_account_proxy()
    await _ensure_oauth_fresh(proxy=proxy)
    return await _run_subprocess(cmd, timeout, env=_proxy_env(proxy), input_data=input_data)


def _manifest_path() -> str:
    return os.path.join(_pool_dir(), "accounts.json")


def _load_manifest() -> dict:
    path = _manifest_path()
    if not os.path.exists(path):
        return {"accounts": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_manifest(manifest: dict) -> None:
    os.makedirs(_pool_dir(), exist_ok=True)
    with open(_manifest_path(), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def get_account_token_and_proxy(account_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Retrieve (token, proxy, account_dir) for a given account (or active account from ~/.gemini)."""
    acc = _find_account(account_id)
    proxy = get_google_proxy(acc.get("proxy") if acc else None)
    if not pool_enabled() or account_id == get_active_account_id() or not acc:
        token = _read_live_access_token(_gemini_home())
        return token, proxy, None

    account_dir = os.path.join(_pool_dir(), "accounts", account_id)
    token = _read_snapshot_access_token(account_dir)
    return token, proxy, account_dir


def _extract_account_email(account_id: str) -> Optional[str]:
    """Helper to get email from google_accounts.json or oauth_creds.json in account dir."""
    account_dir = os.path.join(_pool_dir(), "accounts", account_id)
    g_acc_path = os.path.join(account_dir, "google_accounts.json")
    if os.path.exists(g_acc_path):
        try:
            with open(g_acc_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                email = data.get("active")
                if email:
                    return email
        except Exception:
            pass
    oauth_path = os.path.join(account_dir, "oauth_creds.json")
    if os.path.exists(oauth_path):
        try:
            with open(oauth_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                id_token = data.get("id_token")
                if id_token:
                    parts = id_token.split(".")
                    if len(parts) >= 2:
                        padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                        decoded_jwt = json.loads(base64.urlsafe_b64decode(padded.encode()).decode("utf-8"))
                        return decoded_jwt.get("email")
        except Exception:
            pass
    return None


def list_accounts() -> List[dict]:
    accounts = _load_manifest().get("accounts", [])
    for acc in accounts:
        if not acc.get("email"):
            acc_email = _extract_account_email(acc["id"])
            if acc_email:
                acc["email"] = acc_email
    return accounts


def _find_account(account_id: str) -> Optional[dict]:
    for acc in list_accounts():
        if acc["id"] == account_id:
            return acc
    return None


def _find_account_by_email(email: str) -> Optional[dict]:
    if not email:
        return None
    email_clean = email.strip().lower()
    for acc in list_accounts():
        acc_email = acc.get("email") or _extract_account_email(acc["id"])
        if acc_email and acc_email.strip().lower() == email_clean:
            return acc
    return None


def set_account_proxy(account_id: str, proxy: Optional[str]) -> dict:
    """proxy is a full URL, e.g. http://user:pass@host:port or socks5://host:port.
    Pass None/empty to clear it (account goes back to using no proxy / the host's default)."""
    manifest = _load_manifest()
    for acc in manifest.get("accounts", []):
        if acc["id"] == account_id:
            if proxy:
                acc["proxy"] = proxy
            else:
                acc.pop("proxy", None)
            _save_manifest(manifest)
            return acc
    raise ValueError(f"Unknown pool account: {account_id}")


def _proxy_env(proxy: Optional[str]) -> Optional[dict]:
    """Builds a subprocess env with the given proxy applied, if any -- scoped to that
    one subprocess call only, never mutates the running server's own environment."""
    if not proxy:
        return None
    env = os.environ.copy()
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env[var] = proxy
    return env


def _hash_file(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def current_session_matches_pool() -> Optional[str]:
    """Returns the account_id if the live ~/.gemini/oauth_creds.json matches an
    existing pool snapshot exactly, else None."""
    live_hash = _hash_file(os.path.join(_gemini_home(), "oauth_creds.json"))
    if not live_hash:
        return None
    for acc in list_accounts():
        acc_path = os.path.join(_pool_dir(), "accounts", acc["id"], "oauth_creds.json")
        if _hash_file(acc_path) == live_hash:
            return acc["id"]
    return None


def launch_login_terminal(env: Optional[dict] = None) -> bool:
    """Best-effort: opens a terminal window running `agy auth login` so the user can complete
    whatever login flow it presents (browser-based OAuth). Returns False if no
    terminal could be launched (e.g. a headless Linux server) -- caller should show
    a manual fallback instruction in that case."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.Popen(
                ["cmd", "/c", "start", "AGY Account Login", "cmd", "/k", "agy", "auth", "login"],
                env=env,
            )
            return True
        elif system == "Darwin":
            subprocess.Popen(["osascript", "-e", 'tell app "Terminal" to do script "agy auth login"'], env=env)
            return True
        else:
            subprocess.Popen(["x-terminal-emulator", "-e", "agy auth login"], env=env)
            return True
    except Exception as e:
        logger.warning(f"[pool] Could not launch login terminal: {e}")
        return False


_pending_add_baseline_hash: Optional[str] = None


async def start_add_account_flow(proxy: Optional[str] = None) -> dict:
    auto_added_current = None
    if current_session_matches_pool() is None:
        try:
            record = await snapshot_current_session_to_account(f"current-session-{int(time.time())}")
            auto_added_current = f"Current session auto-added as '{record['label']}'"
        except RuntimeError:
            pass  # no live credentials to snapshot yet -- fine, proceed to login flow

    global _pending_add_baseline_hash
    _pending_add_baseline_hash = _hash_file(os.path.join(_gemini_home(), "oauth_creds.json"))

    terminal_launched = launch_login_terminal(env=_proxy_env(get_google_proxy(proxy)))

    return {
        "auto_added_current": auto_added_current,
        "terminal_launched": terminal_launched,
        "message": (
            "A terminal window was opened. Sign in there with the NEW Google account, "
            "then this page will detect it automatically."
            if terminal_launched
            else "Could not open a terminal automatically. Open one yourself and run "
            "`agy auth login`, sign in with the new account, then this page will detect it."
        ),
    }


async def check_add_account_flow() -> dict:
    if _pending_add_baseline_hash is None:
        return {"pending": False, "changed": False}
    current_hash = _hash_file(os.path.join(_gemini_home(), "oauth_creds.json"))
    changed = current_hash is not None and current_hash != _pending_add_baseline_hash
    return {"pending": True, "changed": changed}


_OAUTH_FLOWS: Dict[str, dict] = {}
_OAUTH_FLOW_TTL = 900  # 15 min


def generate_oauth_auth_url(proxy: Optional[str] = None) -> dict:
    """Generate PKCE auth URL for Antigravity Google OAuth."""
    client_id = os.environ.get("ANTIGRAVITY_CLIENT_ID", "").strip()
    if not client_id:
        raise RuntimeError("ANTIGRAVITY_CLIENT_ID must be set in .env to generate OAuth URLs")

    # Generate PKCE verifier & challenge
    code_verifier = secrets.token_urlsafe(32)
    code_challenge_bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).decode("ascii").rstrip("=")

    state = secrets.token_urlsafe(16)
    flow_id = secrets.token_hex(8)

    scope = (
        "https://www.googleapis.com/auth/cloud-platform "
        "https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/userinfo.profile "
        "https://www.googleapis.com/auth/cclog "
        "https://www.googleapis.com/auth/experimentsandconfigs "
        "https://www.googleapis.com/auth/aicode "
        "openid"
    )
    redirect_uri = "https://antigravity.google/oauth-callback"

    params = {
        "access_type": "offline",
        "client_id": client_id,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "consent",
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    url = f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"

    _OAUTH_FLOWS[flow_id] = {
        "flow_id": flow_id,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "created_at": time.time(),
        "proxy": proxy,
    }

    # Clean old flows
    now = time.time()
    for fid in list(_OAUTH_FLOWS.keys()):
        if now - _OAUTH_FLOWS[fid]["created_at"] > _OAUTH_FLOW_TTL:
            _OAUTH_FLOWS.pop(fid, None)

    return {
        "flow_id": flow_id,
        "url": url,
        "state": state,
        "code_challenge": code_challenge,
    }


async def complete_oauth_flow(
    flow_id: Optional[str],
    code: str,
    label: Optional[str] = None,
    proxy: Optional[str] = None,
    code_verifier: Optional[str] = None,
) -> dict:
    """Exchange authorization code for tokens and store account in pool."""
    flow = _OAUTH_FLOWS.pop(flow_id, None) if flow_id else None
    verifier = code_verifier or (flow.get("code_verifier") if flow else None)
    if not verifier:
        raise ValueError("Missing code_verifier (expired or invalid flow_id)")

    redirect_uri = flow.get("redirect_uri") if flow else "https://antigravity.google/oauth-callback"
    client_id = (flow.get("client_id") if flow else None) or os.environ.get("ANTIGRAVITY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("ANTIGRAVITY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("ANTIGRAVITY_CLIENT_ID and ANTIGRAVITY_CLIENT_SECRET must be set in .env")

    req_proxy = proxy or (flow.get("proxy") if flow else None)
    effective_proxy = get_google_proxy(req_proxy)

    # Clean code in case user pasted full callback URL or raw string
    clean_code = code.strip()
    if "code=" in clean_code:
        try:
            parsed = urllib.parse.urlparse(clean_code)
            qs = urllib.parse.parse_qs(parsed.query or parsed.fragment)
            if "code" in qs:
                clean_code = qs["code"][0]
        except Exception:
            pass

    async with httpx.AsyncClient(**httpx_client_kwargs(proxy=effective_proxy, timeout=30.0)) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": clean_code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "user-agent": "Go-http-client/2.0",
                "accept-encoding": "gzip",
            },
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Google OAuth token exchange failed (HTTP {resp.status_code}): {resp.text[:500]}")

    payload = resp.json()
    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    id_token = payload.get("id_token")
    expires_in = int(payload.get("expires_in", 3600))
    expiry_date = int((time.time() + expires_in) * 1000)

    # Parse email from id_token or userinfo if missing
    email = None
    if id_token:
        try:
            parts = id_token.split(".")
            if len(parts) >= 2:
                padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                decoded_jwt = json.loads(base64.urlsafe_b64decode(padded.encode()).decode("utf-8"))
                email = decoded_jwt.get("email")
        except Exception as e:
            logger.warning(f"[pool] Failed decoding email from id_token: {e}")

    if not email and access_token:
        try:
            async with httpx.AsyncClient(**httpx_client_kwargs(proxy=req_proxy, timeout=10.0)) as client:
                ui_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if ui_resp.status_code == 200:
                    email = ui_resp.json().get("email")
        except Exception as e:
            logger.warning(f"[pool] Failed fetching email from userinfo: {e}")

    # Check if account with same email already exists for deduplication
    existing_acc = _find_account_by_email(email) if email else None
    if existing_acc:
        account_id = existing_acc["id"]
        acc_label = (
            label.strip()
            if label and label.strip()
            else existing_acc.get("label", email.split("@")[0] if email else "account")
        )
        account_dir = os.path.join(_pool_dir(), "accounts", account_id)
        os.makedirs(account_dir, exist_ok=True)
        is_update = True
    else:
        acc_label = label.strip() if label and label.strip() else (email.split("@")[0] if email else "account")
        account_id = f"{_slugify(acc_label)}-{uuid.uuid4().hex[:6]}"
        account_dir = os.path.join(_pool_dir(), "accounts", account_id)
        os.makedirs(account_dir, exist_ok=True)
        is_update = False

    # Write oauth_creds.json
    creds_data = {
        "access_token": access_token,
        "expires_in": expires_in,
        "refresh_token": refresh_token,
        "scope": payload.get("scope", ""),
        "token_type": payload.get("token_type", "Bearer"),
        "id_token": id_token,
        "expiry_date": expiry_date,
    }
    with open(os.path.join(account_dir, "oauth_creds.json"), "w", encoding="utf-8") as f:
        json.dump(creds_data, f, indent=2)

    # Write google_accounts.json
    if email:
        with open(os.path.join(account_dir, "google_accounts.json"), "w", encoding="utf-8") as f:
            json.dump({"active": email, "old": []}, f, indent=2)

    # Generate installation IDs if needed
    for fname in ("installation_id", "antigravity-cli_installation_id", "antigravity_installation_id"):
        id_path = os.path.join(account_dir, fname)
        if not os.path.exists(id_path):
            with open(id_path, "w", encoding="utf-8") as f:
                f.write(str(uuid.uuid4()))

    manifest = _load_manifest()
    accounts_list = manifest.setdefault("accounts", [])
    if is_update:
        for acc in accounts_list:
            if acc["id"] == account_id:
                if label and label.strip():
                    acc["label"] = acc_label
                if email:
                    acc["email"] = email
                if req_proxy is not None:
                    if req_proxy:
                        acc["proxy"] = req_proxy
                    else:
                        acc.pop("proxy", None)
                record = acc
                break
        else:
            record = {"id": account_id, "label": acc_label, "email": email, "added_at": time.time()}
            if req_proxy:
                record["proxy"] = req_proxy
            accounts_list.append(record)
    else:
        record = {"id": account_id, "label": acc_label, "email": email, "added_at": time.time()}
        if req_proxy:
            record["proxy"] = req_proxy
        accounts_list.append(record)

    _save_manifest(manifest)

    # Clear quota cache for this account
    oauth_refresh.clear_quota_summary_cache(access_token)

    # If this is the currently active account in ~/.gemini, sync updated credentials to ~/.gemini immediately
    if account_id == get_active_account_id():
        try:
            await activate_account(account_id)
        except Exception as e:
            logger.warning(f"[pool] Failed reactivating updated account {account_id}: {e}")

    await stats_store.upsert_pool_account_state(
        account_id, status="healthy", consecutive_failures=0, cooldown_until=None
    )
    logger.info(
        f"[pool] {'Updated' if is_update else 'Created'} account {account_id} via direct OAuth PKCE (email={email})"
    )

    # If no active account is set or activated, activate this one
    if not get_active_account_id():
        try:
            await activate_account(account_id)
        except Exception:
            pass

    return {
        "id": account_id,
        "label": acc_label,
        "email": email,
        "added_at": record.get("added_at", time.time()),
        "proxy": record.get("proxy"),
        "updated": is_update,
    }


def cancel_add_account_flow() -> None:
    global _pending_add_baseline_hash
    _pending_add_baseline_hash = None


def get_active_account_id() -> Optional[str]:
    """In-memory accessor -- safe to call from a sync context after run_agy_prompt returns."""
    return _active_account_id


def get_active_account_proxy() -> Optional[str]:
    account_id = get_active_account_id()
    account_proxy = None
    if account_id:
        account = _find_account(account_id)
        account_proxy = account.get("proxy") if account else None
    return get_google_proxy(account_proxy)


async def _ensure_oauth_fresh(proxy: Optional[str] = None, pool_account_id: Optional[str] = None) -> None:
    target_id = pool_account_id or get_active_account_id()
    try:
        refreshed = await oauth_refresh.ensure_fresh_antigravity_token(
            _gemini_home(),
            proxy=proxy,
            pool_account_id=target_id,
        )
        if refreshed and pool_enabled() and target_id:
            await sync_back_credentials(target_id)
    except Exception as e:
        logger.warning(
            "[oauth] ensure_fresh_credentials failed (pool_account=%s): %s",
            target_id or "none",
            e,
        )


async def init_pool_state() -> None:
    """Best-effort restore of the in-memory active-account pointer from the DB after a restart.

    Does not verify the on-disk ~/.gemini state actually matches -- if the process crashed
    between activating an account and using it, the next execute_agy() call will re-check
    and re-activate as needed anyway (activate_account is idempotent).
    """
    global _active_account_id
    if not pool_enabled():
        return
    try:
        _active_account_id = await stats_store.get_active_account_id_db()
    except Exception as e:
        logger.warning(f"Failed to restore pool active account from DB: {e}")

    accounts = list_accounts()
    if accounts:
        target_id = (
            _active_account_id if _active_account_id and _find_account(_active_account_id) else accounts[0]["id"]
        )
        try:
            await activate_account(target_id)
        except Exception as e:
            logger.warning(f"[pool] Failed initial activation of account {target_id}: {e}")


async def activate_account(account_id: str) -> None:
    account = _find_account(account_id)
    if account is None:
        raise ValueError(f"Unknown pool account: {account_id}")

    account_dir = os.path.join(_pool_dir(), "accounts", account_id)
    gemini_home = _gemini_home()
    proxy = get_google_proxy(account.get("proxy"))

    for src_name, dest_rel in CREDENTIAL_FILES:
        src = os.path.join(account_dir, src_name)
        if not os.path.exists(src):
            continue
        dest = os.path.join(gemini_home, dest_rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".tmp"
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)

    oauth_refresh.clear_active_credential_cache()
    global _active_account_id
    _active_account_id = account_id
    await stats_store.set_active_account_id_db(account_id)
    await stats_store.upsert_pool_account_state(account_id, last_used_ts=time.time())
    await _ensure_oauth_fresh(proxy=proxy, pool_account_id=account_id)
    logger.info(f"[pool] Activated account {account_id}")


async def sync_back_credentials(account_id: str) -> None:
    """Best-effort: copy the live ~/.gemini credential files back into the pool
    snapshot after our own OAuth refresh or agy credential updates.
    Never raises -- a failure here must not break the actual API response.
    """
    try:
        account_dir = os.path.join(_pool_dir(), "accounts", account_id)
        gemini_home = _gemini_home()
        os.makedirs(account_dir, exist_ok=True)
        for src_name, dest_rel in CREDENTIAL_FILES:
            src_host = os.path.join(gemini_home, dest_rel)
            if not os.path.exists(src_host):
                continue
            shutil.copyfile(src_host, os.path.join(account_dir, src_name))
    except Exception as e:
        logger.warning(f"[pool] sync_back_credentials failed for {account_id}: {e}")


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", label.strip().lower()).strip("-")
    return slug or "account"


async def snapshot_current_session_to_account(label: str, proxy: Optional[str] = None) -> dict:
    """Adopts whatever is currently logged into ~/.gemini as a new pool account.
    Caller is expected to have already run `agy auth login` for the account they want to add.
    """
    account_id = f"{_slugify(label)}-{uuid.uuid4().hex[:6]}"
    account_dir = os.path.join(_pool_dir(), "accounts", account_id)
    os.makedirs(account_dir, exist_ok=True)
    gemini_home = _gemini_home()

    copied_any = False
    for src_name, dest_rel in CREDENTIAL_FILES:
        src_host = os.path.join(gemini_home, dest_rel)
        if os.path.exists(src_host):
            shutil.copyfile(src_host, os.path.join(account_dir, src_name))
            copied_any = True

    if not copied_any:
        shutil.rmtree(account_dir, ignore_errors=True)
        raise RuntimeError(
            "No agy credential files found under the current ~/.gemini session -- "
            "run `agy auth login` first, then retry."
        )

    manifest = _load_manifest()
    record = {"id": account_id, "label": label, "added_at": time.time()}
    if proxy:
        record["proxy"] = proxy
    manifest.setdefault("accounts", []).append(record)
    _save_manifest(manifest)
    await stats_store.upsert_pool_account_state(account_id, status="healthy")
    logger.info(f"[pool] Snapshotted current session as new account {account_id} ({label})")
    return record


async def delete_account(account_id: str) -> None:
    manifest = _load_manifest()
    manifest["accounts"] = [a for a in manifest.get("accounts", []) if a["id"] != account_id]
    _save_manifest(manifest)
    account_dir = os.path.join(_pool_dir(), "accounts", account_id)
    if os.path.isdir(account_dir):
        shutil.rmtree(account_dir, ignore_errors=True)


async def dedupe_accounts_by_email() -> List[str]:
    """Collapses accounts that resolve to the same Google email, keeping the most
    recently added one (freshest credentials). Accounts whose email can't be
    determined are left alone. Returns the removed account ids."""
    manifest = _load_manifest()
    seen: Set[str] = set()
    removed: List[str] = []

    for acc in sorted(manifest.get("accounts", []), key=lambda a: a.get("added_at") or 0, reverse=True):
        email = (acc.get("email") or _extract_account_email(acc["id"]) or "").strip().lower()
        if not email:
            continue
        acc["email"] = email  # backfill so the manifest stops needing the on-disk lookup
        if email in seen:
            removed.append(acc["id"])
        else:
            seen.add(email)

    manifest["accounts"] = [a for a in manifest.get("accounts", []) if a["id"] not in removed]
    _save_manifest(manifest)

    # The credential snapshots are deliberately left on disk -- dropping them from
    # the manifest is enough to stop rotation using them, and keeping the files
    # makes an accidental dedupe recoverable by hand.
    for account_id in removed:
        logger.info(f"[pool] Dropped duplicate account {account_id} from manifest")
    return removed


def pin_session_account(session_hash: str, account_id: str) -> None:
    if not session_hash:
        return
    _SESSION_AFFINITY[session_hash] = (account_id, time.time() + _AFFINITY_TTL)


def get_pinned_account(session_hash: str) -> Optional[str]:
    if not session_hash:
        return None
    entry = _SESSION_AFFINITY.get(session_hash)
    if not entry:
        return None
    acc_id, expire_at = entry
    if time.time() > expire_at:
        _SESSION_AFFINITY.pop(session_hash, None)
        return None
    return acc_id


def compute_prompt_prefix_hash(system: Optional[str] = None, messages: Optional[List[dict]] = None) -> str:
    seed = system or ""
    if messages and len(messages) > 0:
        first_msg = messages[0].get("content", "") if isinstance(messages[0], dict) else str(messages[0])
        seed += f"|{first_msg}"[:2000]
    if not seed:
        return ""
    return hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:16]


def get_account_model_cooldowns(account_id: str) -> Dict[str, float]:
    now = time.time()
    cooldowns = _MODEL_COOLDOWNS.get(account_id, {})
    return {m: t for m, t in cooldowns.items() if t > now}


async def select_next_healthy_account(
    exclude: Set[str] = frozenset(),
    model: Optional[str] = None,
    session_hash: Optional[str] = None,
) -> Optional[dict]:
    accounts = [a for a in list_accounts() if a["id"] not in exclude]
    if not accounts:
        return None

    now = time.time()
    candidates: List[dict] = []
    active_id = get_active_account_id()

    for acc in accounts:
        state = await stats_store.get_pool_account_state(acc["id"]) or {}
        status = state.get("status", "healthy")
        cooldown_until = state.get("cooldown_until")

        if status == "cooldown" and cooldown_until and now > cooldown_until:
            await stats_store.upsert_pool_account_state(
                acc["id"], status="healthy", cooldown_until=None, consecutive_failures=0
            )
            status = "healthy"

        # Check per-model cooldown
        if model and acc["id"] in _MODEL_COOLDOWNS:
            if _MODEL_COOLDOWNS[acc["id"]].get(model, 0) > now:
                continue

        if status == "healthy":
            candidates.append(acc)

    if not candidates:
        return None

    # Check Session Affinity first
    if session_hash:
        pinned_acc_id = get_pinned_account(session_hash)
        if pinned_acc_id and pinned_acc_id not in exclude:
            for acc in candidates:
                if acc["id"] == pinned_acc_id:
                    return acc

    # Sticky account preference: if currently active account is healthy and not excluded
    if active_id and active_id not in exclude:
        for acc in candidates:
            if acc["id"] == active_id:
                return acc

    return candidates[0]


async def mark_success(account_id: str, session_hash: Optional[str] = None) -> None:
    if session_hash:
        pin_session_account(session_hash, account_id)
    await stats_store.upsert_pool_account_state(account_id, status="healthy", consecutive_failures=0)


async def mark_rate_limited(account_id: str, cooldown_seconds: int = 60, model: Optional[str] = None) -> None:
    now = time.time()
    if model:
        if account_id not in _MODEL_COOLDOWNS:
            _MODEL_COOLDOWNS[account_id] = {}
        _MODEL_COOLDOWNS[account_id][model] = now + cooldown_seconds
        logger.info(f"[pool] Account {account_id} model {model} in cooldown for {cooldown_seconds}s")
    else:
        await stats_store.upsert_pool_account_state(
            account_id, status="cooldown", cooldown_until=now + cooldown_seconds
        )


async def mark_failure(account_id: str) -> None:
    state = await stats_store.get_pool_account_state(account_id) or {}
    failures = (state.get("consecutive_failures") or 0) + 1
    status = "unhealthy" if failures >= 3 else state.get("status", "healthy")
    await stats_store.upsert_pool_account_state(account_id, consecutive_failures=failures, status=status)


async def check_and_recover_account_health(account_id: str) -> dict:
    """Active healthcheck: queries Google Quota API with force=True for this account.
    If the quota check succeeds and quotas have remaining headroom (or check passed 200),
    resets cooldown/unhealthy status to healthy.
    """
    token, proxy, account_dir = get_account_token_and_proxy(account_id)
    if not token and not account_dir:
        return {"account_id": account_id, "status": "unknown", "recovered": False, "reason": "No credentials found"}

    try:
        quota_data = await oauth_refresh.retrieve_account_quota(
            account_dir=account_dir,
            access_token=token,
            proxy=proxy,
            pool_account_id=account_id,
            force=True,
        )
        gemini_5h = quota_data.get("gemini_5h")
        claude_5h = quota_data.get("claude_5h")
        has_quota = (gemini_5h is None or gemini_5h > 0.0) and (claude_5h is None or claude_5h > 0.0)

        if has_quota:
            await stats_store.upsert_pool_account_state(
                account_id, status="healthy", cooldown_until=None, consecutive_failures=0
            )
            return {
                "account_id": account_id,
                "status": "healthy",
                "recovered": True,
                "quota": quota_data,
                "message": "Account is healthy and ready for requests",
            }
        else:
            return {
                "account_id": account_id,
                "status": "cooldown",
                "recovered": False,
                "quota": quota_data,
                "message": "Quota limit still exhausted (5h remaining is 0%)",
            }
    except Exception as e:
        logger.warning(f"[pool] check_and_recover_account_health failed for {account_id}: {e}")
        return {
            "account_id": account_id,
            "status": "unhealthy",
            "recovered": False,
            "error": str(e),
            "message": f"Health check failed: {e}",
        }


async def _run_subprocess(
    cmd: List[str], timeout: Optional[float], env: Optional[dict] = None, input_data: Optional[bytes] = None
) -> Tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if input_data is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    if timeout:
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(input=input_data), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            raise
    else:
        stdout, stderr = await process.communicate(input=input_data)
    return process.returncode, stdout, stderr


async def acquire_http_account(
    exclude: Set[str] = frozenset(),
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Pool-aware credential acquisition for the HTTP transport.

    Swaps ~/.gemini to the least-recently-used healthy account and returns
    (account_id, proxy, access_token). The lock is only held while credentials
    are swapped and the token is read -- once the bearer token is in hand the
    request no longer depends on what's on disk, so concurrent streams don't
    serialize the way execute_agy() has to for subprocesses.

    Returns (None, proxy, token) when the pool is disabled.
    """
    if not pool_enabled():
        proxy = get_active_account_proxy()
        await _ensure_oauth_fresh(proxy=proxy)
        return None, proxy, _read_live_access_token(_gemini_home())

    async with _LOCK:
        account = await select_next_healthy_account(exclude=exclude)
        if account is None:
            raise RuntimeError("All pool accounts are rate-limited or unhealthy")

        proxy = get_google_proxy(account.get("proxy"))
        if get_active_account_id() != account["id"]:
            await activate_account(account["id"])
        else:
            await _ensure_oauth_fresh(proxy=proxy, pool_account_id=account["id"])
        return account["id"], proxy, _read_live_access_token(_gemini_home())


async def execute_agy(
    cmd: List[str], timeout: Optional[float] = None, input_data: Optional[bytes] = None
) -> Tuple[int, bytes, bytes]:
    """Pool-aware wrapper around every agy CLI subprocess call.

    Disabled (default): runs cmd directly, unlocked -- identical to pre-pool behavior.

    Enabled: holds the pool lock for the ENTIRE call including any rotation retries.
    OAuth tokens are refreshed by oauth_refresh before each call; releasing the lock
    earlier would let a concurrent request swap credential files out from under an
    in-flight process. Since agy is a single global logged-in session on disk regardless,
    full serialization costs nothing that wasn't already implicit.
    """
    if not pool_enabled():
        proxy = get_active_account_proxy()
        await _ensure_oauth_fresh(proxy=proxy)
        return await _run_subprocess(cmd, timeout, env=_proxy_env(proxy), input_data=input_data)

    async with _LOCK:
        max_attempts = int(os.environ.get("AGY_POOL_MAX_RETRIES", "3"))
        excluded: Set[str] = set()
        last_stderr = b""

        for _ in range(max_attempts):
            account = await select_next_healthy_account(exclude=excluded)
            if account is None:
                raise RuntimeError("All pool accounts are rate-limited or unhealthy")

            if get_active_account_id() != account["id"]:
                await activate_account(account["id"])
            else:
                proxy = get_google_proxy(account.get("proxy"))
                await _ensure_oauth_fresh(proxy=proxy)

            proxy = get_google_proxy(account.get("proxy"))
            env = _proxy_env(proxy)
            returncode, stdout, stderr = await _run_subprocess(cmd, timeout, env=env, input_data=input_data)
            await sync_back_credentials(account["id"])

            if returncode == 0:
                await mark_success(account["id"])
                return returncode, stdout, stderr

            combined = (stderr.decode(errors="ignore") + stdout.decode(errors="ignore")).lower()
            if any(sig in combined for sig in RATE_LIMIT_SIGNALS):
                cooldown = int(os.environ.get("AGY_POOL_COOLDOWN_SECONDS", "3600"))
                await mark_rate_limited(account["id"], cooldown)
                excluded.add(account["id"])
                last_stderr = stderr
                logger.warning(f"[pool] Account {account['id']} rate-limited, rotating")
                continue
            else:
                await mark_failure(account["id"])
                return returncode, stdout, stderr

        raise RuntimeError(
            f"Exceeded pool retry limit ({max_attempts}); all attempted accounts rate-limited. "
            f"Last error: {last_stderr.decode(errors='ignore')[:500]}"
        )


# ---- git sync -------------------------------------------------------------------


def _git_sync(*args: str) -> str:
    result = subprocess.run(["git", "-C", _pool_dir(), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


async def git_pull() -> str:
    return await asyncio.to_thread(_git_sync, "pull")


def _git_commit_and_push_sync(message: str) -> str:
    _git_sync("add", "-A")
    result = subprocess.run(["git", "-C", _pool_dir(), "commit", "-m", message], capture_output=True, text=True)
    if result.returncode != 0 and "nothing to commit" not in result.stdout.lower():
        raise RuntimeError(f"git commit failed: {result.stderr.strip()}")
    return _git_sync("push")


async def git_commit_and_push(message: str = "Update account pool") -> str:
    return await asyncio.to_thread(_git_commit_and_push_sync, message)
