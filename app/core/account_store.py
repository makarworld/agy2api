import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("AGY_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"))
_DB_PATH = os.environ.get("AGY_DB_PATH", os.path.join(_DATA_DIR, "stats.db"))
_JSON_ACCOUNTS_FILE = os.environ.get("ACCOUNTS_FILE", os.path.join(_DATA_DIR, "accounts.json"))

def get_db_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_accounts_table() -> None:
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                email TEXT,
                proxy TEXT,
                refresh_token TEXT NOT NULL,
                client_id TEXT,
                client_secret TEXT,
                access_token TEXT,
                token_expiry REAL DEFAULT 0,
                project_id TEXT,
                status TEXT NOT NULL DEFAULT 'healthy',
                backoff_until REAL DEFAULT 0,
                last_used_at REAL DEFAULT 0,
                consecutive_errors INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status, backoff_until);")
        conn.commit()

def sync_accounts_from_json(json_path: Optional[str] = None) -> int:
    path = json_path or _JSON_ACCOUNTS_FILE
    if not os.path.exists(path):
        return 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"[account_store] Failed to read {path}: {e}")
        return 0

    acc_list = []
    if isinstance(data, list):
        acc_list = data
    elif isinstance(data, dict):
        acc_list = data.get("accounts", [])

    now = time.time()
    count = 0
    init_accounts_table()

    with get_db_connection() as conn:
        for item in acc_list:
            if not isinstance(item, dict):
                continue
            acc_id = str(item.get("id") or item.get("name") or item.get("email") or f"acc_{count+1}")
            refresh_token = item.get("refresh_token") or (item.get("credentials", {}).get("refresh_token") if isinstance(item.get("credentials"), dict) else None)
            if not refresh_token:
                continue

            email = item.get("email") or ""
            proxy = item.get("proxy") or ""
            client_id = item.get("client_id") or (item.get("credentials", {}).get("client_id") if isinstance(item.get("credentials"), dict) else "")
            client_secret = item.get("client_secret") or (item.get("credentials", {}).get("client_secret") if isinstance(item.get("credentials"), dict) else "")
            access_token = item.get("access_token") or (item.get("credentials", {}).get("access_token") if isinstance(item.get("credentials"), dict) else "")
            project_id = item.get("project_id") or ""

            cursor = conn.cursor()
            cursor.execute("SELECT id, access_token, token_expiry, status, backoff_until FROM accounts WHERE id = ?", (acc_id,))
            existing = cursor.fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE accounts
                    SET email = ?, proxy = ?, refresh_token = ?, client_id = ?, client_secret = ?,
                        project_id = COALESCE(NULLIF(?, ''), project_id),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (email, proxy, refresh_token, client_id, client_secret, project_id, now, acc_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO accounts (
                        id, email, proxy, refresh_token, client_id, client_secret,
                        access_token, token_expiry, project_id, status, backoff_until,
                        last_used_at, consecutive_errors, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'healthy', 0, 0, 0, ?, ?)
                    """,
                    (acc_id, email, proxy, refresh_token, client_id, client_secret, access_token, 0, project_id, now, now),
                )
            count += 1
        conn.commit()

    logger.info(f"[account_store] Synced {count} accounts from {path}")
    return count

def get_account_by_id(account_id: str) -> Optional[Dict[str, Any]]:
    init_accounts_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_accounts() -> List[Dict[str, Any]]:
    init_accounts_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts ORDER BY last_used_at ASC")
        return [dict(row) for row in cursor.fetchall()]

def select_next_healthy_account(exclude_ids: Optional[set] = None) -> Optional[Dict[str, Any]]:
    init_accounts_table()
    exclude = exclude_ids or set()
    now = time.time()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM accounts
            WHERE status != 'disabled'
              AND (backoff_until <= ? OR status = 'healthy')
            ORDER BY last_used_at ASC
            """,
            (now,),
        )
        rows = cursor.fetchall()
        for row in rows:
            acc = dict(row)
            if acc["id"] not in exclude:
                return acc
    return None

def update_account_tokens(account_id: str, access_token: str, token_expiry: float, project_id: Optional[str] = None) -> None:
    now = time.time()
    with get_db_connection() as conn:
        if project_id:
            conn.execute(
                """
                UPDATE accounts
                SET access_token = ?, token_expiry = ?, project_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (access_token, token_expiry, project_id, now, account_id),
            )
        else:
            conn.execute(
                """
                UPDATE accounts
                SET access_token = ?, token_expiry = ?, updated_at = ?
                WHERE id = ?
                """,
                (access_token, token_expiry, now, account_id),
            )
        conn.commit()

def mark_account_used(account_id: str) -> None:
    now = time.time()
    with get_db_connection() as conn:
        conn.execute("UPDATE accounts SET last_used_at = ? WHERE id = ?", (now, account_id))
        conn.commit()

def mark_account_rate_limited(account_id: str, cooldown_seconds: float = 300.0) -> None:
    now = time.time()
    backoff = now + cooldown_seconds
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE accounts
            SET status = 'exhausted_429',
                backoff_until = ?,
                consecutive_errors = consecutive_errors + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (backoff, now, account_id),
        )
        conn.commit()

def mark_account_healthy(account_id: str) -> None:
    now = time.time()
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE accounts
            SET status = 'healthy',
                backoff_until = 0,
                consecutive_errors = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (now, account_id),
        )
        conn.commit()


def upsert_account(
    *,
    account_id: str,
    email: str = "",
    proxy: str = "",
    refresh_token: str,
    client_id: str = "",
    client_secret: str = "",
    access_token: str = "",
    token_expiry: float = 0,
    project_id: str = "",
) -> None:
    """Insert or update a single account row in SQLite."""
    init_accounts_table()
    now = time.time()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM accounts WHERE id = ?", (account_id,))
        if cursor.fetchone():
            conn.execute(
                """
                UPDATE accounts
                SET email = ?, proxy = ?, refresh_token = ?, client_id = ?, client_secret = ?,
                    access_token = COALESCE(NULLIF(?, ''), access_token),
                    token_expiry = CASE WHEN ? > 0 THEN ? ELSE token_expiry END,
                    project_id = COALESCE(NULLIF(?, ''), project_id),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    email,
                    proxy,
                    refresh_token,
                    client_id,
                    client_secret,
                    access_token,
                    token_expiry,
                    token_expiry,
                    project_id,
                    now,
                    account_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO accounts (
                    id, email, proxy, refresh_token, client_id, client_secret,
                    access_token, token_expiry, project_id, status, backoff_until,
                    last_used_at, consecutive_errors, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'healthy', 0, 0, 0, ?, ?)
                """,
                (
                    account_id,
                    email,
                    proxy,
                    refresh_token,
                    client_id,
                    client_secret,
                    access_token,
                    token_expiry,
                    project_id,
                    now,
                    now,
                ),
            )
        conn.commit()


def _read_pool_oauth_creds(account_dir: str) -> Optional[Dict[str, Any]]:
    for filename in ("oauth_creds.json", "antigravity-oauth-token"):
        path = os.path.join(account_dir, filename)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if filename == "antigravity-oauth-token":
            token_obj = data.get("token") or {}
            refresh_token = token_obj.get("refresh_token")
            access_token = token_obj.get("access_token") or ""
            expiry_raw = token_obj.get("expiry")
        else:
            refresh_token = data.get("refresh_token")
            access_token = data.get("access_token") or ""
            expiry_raw = data.get("expiry_date", data.get("expiry"))
        if not refresh_token:
            continue
        expiry_ts = 0.0
        if isinstance(expiry_raw, (int, float)) and expiry_raw:
            expiry_ts = float(expiry_raw) / 1000.0 if expiry_raw > 1_000_000_000_000 else float(expiry_raw)
        return {
            "refresh_token": refresh_token,
            "access_token": access_token,
            "token_expiry": expiry_ts,
        }
    return None


def sync_accounts_from_pool_manifest(pool_dir: Optional[str] = None) -> int:
    """Import accounts from legacy ~/.agy2api-pool manifest + credential snapshots."""
    pool_path = pool_dir or os.path.expanduser(os.environ.get("AGY_POOL_DIR", "~/.agy2api-pool"))
    manifest_path = os.path.join(pool_path, "accounts.json")
    if not os.path.exists(manifest_path):
        return 0

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        logger.error(f"[account_store] Failed to read pool manifest {manifest_path}: {e}")
        return 0

    count = 0
    init_accounts_table()
    for item in manifest.get("accounts", []):
        if not isinstance(item, dict):
            continue
        acc_id = str(item.get("id") or "").strip()
        if not acc_id:
            continue
        creds = _read_pool_oauth_creds(os.path.join(pool_path, "accounts", acc_id))
        if not creds:
            continue
        upsert_account(
            account_id=acc_id,
            email=str(item.get("email") or ""),
            proxy=str(item.get("proxy") or ""),
            refresh_token=creds["refresh_token"],
            access_token=creds.get("access_token") or "",
            token_expiry=float(creds.get("token_expiry") or 0),
        )
        count += 1

    if count:
        logger.info(f"[account_store] Imported {count} accounts from pool manifest {manifest_path}")
    return count


def sync_all_account_sources() -> int:
    """Sync accounts.json first, then fall back to legacy pool manifest."""
    count = sync_accounts_from_json()
    if count == 0:
        count = sync_accounts_from_pool_manifest()
    return count


def has_accounts() -> bool:
    init_accounts_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM accounts")
        row = cursor.fetchone()
        return bool(row and row[0] > 0)
