import asyncio
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import time
import uuid
from typing import List, Optional, Set, Tuple

from app.core import oauth_refresh
from app.core import stats_store

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
    await _ensure_oauth_fresh(proxy=get_active_account_proxy())
    return await _run_subprocess(cmd, timeout, input_data=input_data)


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


def list_accounts() -> List[dict]:
    return _load_manifest().get("accounts", [])


def _find_account(account_id: str) -> Optional[dict]:
    for acc in list_accounts():
        if acc["id"] == account_id:
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
    """Best-effort: opens a terminal window running `gemini` so the user can complete
    whatever login flow it presents (browser-based OAuth). Returns False if no
    terminal could be launched (e.g. a headless Linux server) -- caller should show
    a manual fallback instruction in that case."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.Popen(
                ["cmd", "/c", "start", "AGY Account Login", "cmd", "/k", "gemini"],
                env=env,
            )
            return True
        elif system == "Darwin":
            subprocess.Popen(["osascript", "-e", 'tell app "Terminal" to do script "gemini"'], env=env)
            return True
        else:
            subprocess.Popen(["x-terminal-emulator", "-e", "gemini"], env=env)
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

    terminal_launched = launch_login_terminal(env=_proxy_env(proxy))

    return {
        "auto_added_current": auto_added_current,
        "terminal_launched": terminal_launched,
        "message": (
            "A terminal window was opened. Sign in there with the NEW Google account, "
            "then this page will detect it automatically."
            if terminal_launched
            else "Could not open a terminal automatically. Open one yourself and run "
                 "`gemini`, sign in with the new account, then this page will detect it."
        ),
    }


async def check_add_account_flow() -> dict:
    if _pending_add_baseline_hash is None:
        return {"pending": False, "changed": False}
    current_hash = _hash_file(os.path.join(_gemini_home(), "oauth_creds.json"))
    changed = current_hash is not None and current_hash != _pending_add_baseline_hash
    return {"pending": True, "changed": changed}


def cancel_add_account_flow() -> None:
    global _pending_add_baseline_hash
    _pending_add_baseline_hash = None


def get_active_account_id() -> Optional[str]:
    """In-memory accessor -- safe to call from a sync context after run_agy_prompt returns."""
    return _active_account_id


def get_active_account_proxy() -> Optional[str]:
    account_id = get_active_account_id()
    if not account_id:
        return None
    account = _find_account(account_id)
    return account.get("proxy") if account else None


async def _ensure_oauth_fresh(proxy: Optional[str] = None) -> None:
    try:
        refreshed = await oauth_refresh.ensure_fresh_antigravity_token(
            _gemini_home(),
            proxy=proxy,
            pool_account_id=get_active_account_id(),
        )
        if refreshed and pool_enabled() and get_active_account_id():
            await sync_back_credentials(get_active_account_id())
    except Exception as e:
        logger.warning(
            "[oauth] ensure_fresh_credentials failed (pool_account=%s): %s",
            get_active_account_id() or "none",
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


async def activate_account(account_id: str) -> None:
    account = _find_account(account_id)
    if account is None:
        raise ValueError(f"Unknown pool account: {account_id}")

    account_dir = os.path.join(_pool_dir(), "accounts", account_id)
    gemini_home = _gemini_home()
    proxy = account.get("proxy")

    live_token = _read_live_access_token(gemini_home)
    snapshot_token = _read_snapshot_access_token(account_dir)
    live_valid = bool(live_token and await oauth_refresh.verify_access_token(live_token, proxy=proxy))
    snapshot_valid = bool(snapshot_token and await oauth_refresh.verify_access_token(snapshot_token, proxy=proxy))

    if live_valid and not snapshot_valid:
        logger.warning(
            "[pool] Skipping credential swap for %s — live ~/.gemini token verifies via quota, snapshot stale",
            account_id,
        )
    else:
        for src_name, dest_rel in CREDENTIAL_FILES:
            src = os.path.join(account_dir, src_name)
            if not os.path.exists(src):
                continue
            dest = os.path.join(gemini_home, dest_rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = dest + ".tmp"
            shutil.copyfile(src, tmp)
            os.replace(tmp, dest)

    global _active_account_id
    _active_account_id = account_id
    await stats_store.set_active_account_id_db(account_id)
    await stats_store.upsert_pool_account_state(account_id, last_used_ts=time.time())
    await _ensure_oauth_fresh(proxy=proxy)
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


async def select_next_healthy_account(exclude: Set[str] = frozenset()) -> Optional[dict]:
    accounts = [a for a in list_accounts() if a["id"] not in exclude]
    if not accounts:
        return None

    now = time.time()
    candidates: List[Tuple[dict, float]] = []
    for acc in accounts:
        state = await stats_store.get_pool_account_state(acc["id"]) or {}
        status = state.get("status", "healthy")
        cooldown_until = state.get("cooldown_until")

        if status == "cooldown" and cooldown_until and now > cooldown_until:
            await stats_store.upsert_pool_account_state(
                acc["id"], status="healthy", cooldown_until=None, consecutive_failures=0
            )
            status = "healthy"

        if status == "healthy":
            candidates.append((acc, state.get("last_used_ts") or 0))

    if not candidates:
        return None

    # Least-recently-used first -- a simple, effective round-robin.
    candidates.sort(key=lambda pair: pair[1])
    return candidates[0][0]


async def mark_success(account_id: str) -> None:
    await stats_store.upsert_pool_account_state(account_id, status="healthy", consecutive_failures=0)


async def mark_rate_limited(account_id: str, cooldown_seconds: int) -> None:
    await stats_store.upsert_pool_account_state(
        account_id, status="cooldown", cooldown_until=time.time() + cooldown_seconds
    )


async def mark_failure(account_id: str) -> None:
    state = await stats_store.get_pool_account_state(account_id) or {}
    failures = (state.get("consecutive_failures") or 0) + 1
    status = "unhealthy" if failures >= 3 else state.get("status", "healthy")
    await stats_store.upsert_pool_account_state(account_id, consecutive_failures=failures, status=status)


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
        await _ensure_oauth_fresh(proxy=get_active_account_proxy())
        return await _run_subprocess(cmd, timeout, input_data=input_data)

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
                await _ensure_oauth_fresh(proxy=account.get("proxy"))

            env = _proxy_env(account.get("proxy"))
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
    result = subprocess.run(
        ["git", "-C", _pool_dir(), *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


async def git_pull() -> str:
    return await asyncio.to_thread(_git_sync, "pull")


def _git_commit_and_push_sync(message: str) -> str:
    _git_sync("add", "-A")
    result = subprocess.run(
        ["git", "-C", _pool_dir(), "commit", "-m", message], capture_output=True, text=True
    )
    if result.returncode != 0 and "nothing to commit" not in result.stdout.lower():
        raise RuntimeError(f"git commit failed: {result.stderr.strip()}")
    return _git_sync("push")


async def git_commit_and_push(message: str = "Update account pool") -> str:
    return await asyncio.to_thread(_git_commit_and_push_sync, message)
