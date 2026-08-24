import asyncio
import os
import sqlite3
import time
import logging
import hashlib
import uuid
from typing import Optional, List, Dict, Any, Tuple

from app.core.token_stats import request_total_tokens

logger = logging.getLogger(__name__)

def extract_chat_metadata(
    headers: Optional[Dict[str, str]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    user_identifier: Optional[str] = None,
    system_text: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Extracts or computes (chat_id, chat_title, prompt_preview).
    """
    chat_id = None
    if headers:
        for key in ("x-session-id", "x-conversation-id", "x-chat-id", "session-id", "conversation-id", "x-request-id"):
            val = headers.get(key)
            if val and val.strip():
                chat_id = val.strip()
                break

    if not chat_id and user_identifier and str(user_identifier).strip():
        chat_id = str(user_identifier).strip()

    messages = messages or []
    first_user_text = ""
    last_user_text = ""

    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            first_user_text = m.get("content", "")
            break
    if not first_user_text and messages:
        first_user_text = messages[0].get("content", "") if isinstance(messages[0], dict) else str(messages[0])

    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            last_user_text = m.get("content", "")
            break
    if not last_user_text and messages:
        last_user_text = messages[-1].get("content", "") if isinstance(messages[-1], dict) else str(messages[-1])

    if not chat_id:
        seed = first_user_text or system_text or ""
        if seed:
            chat_id = "chat_" + hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:12]
        else:
            chat_id = "chat_" + uuid.uuid4().hex[:12]

    chat_title = first_user_text.strip().replace("\n", " ")[:150] if first_user_text else (system_text.strip().replace("\n", " ")[:150] if system_text else "Chat Session")
    prompt_preview = last_user_text.strip()[:1000] if last_user_text else ""

    return chat_id, chat_title, prompt_preview


_DB_PATH = "app/data/stats.db"

_DDL = """
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    endpoint TEXT NOT NULL,
    model TEXT,
    pool_account TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cache_tokens INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL,
    latency_ms INTEGER,
    error_type TEXT,
    chat_id TEXT,
    chat_title TEXT,
    prompt_preview TEXT,
    response_preview TEXT
);

CREATE TABLE IF NOT EXISTS availability_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    event_type TEXT NOT NULL,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_avail_ts ON availability_events(ts);

CREATE TABLE IF NOT EXISTS pool_account_state (
    account_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'healthy',
    cooldown_until REAL,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_used_ts REAL,
    total_requests INTEGER NOT NULL DEFAULT 0,
    total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    total_completion_tokens INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pool_runtime (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active_account_id TEXT
);
"""


def init_db(db_path: str = None) -> None:
    global _DB_PATH
    if db_path:
        _DB_PATH = db_path
    os.makedirs(os.path.dirname(_DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.executescript(_DDL)
        # Migrate existing table if columns are missing
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(requests)").fetchall()}
        for col_name, col_type in [
            ("chat_id", "TEXT"),
            ("chat_title", "TEXT"),
            ("prompt_preview", "TEXT"),
            ("response_preview", "TEXT"),
        ]:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE requests ADD COLUMN {col_name} {col_type}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_account ON requests(pool_account)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_chat_id ON requests(chat_id)")
        conn.commit()
    finally:
        conn.close()
    logger.info(f"Stats DB initialized at {_DB_PATH}")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---- requests / availability -------------------------------------------------

def _record_request_sync(
    endpoint: str,
    model: Optional[str],
    pool_account: Optional[str],
    prompt_tokens: int,
    completion_tokens: int,
    cache_tokens: int,
    success: bool,
    latency_ms: Optional[int],
    error_type: Optional[str],
    chat_id: Optional[str] = None,
    chat_title: Optional[str] = None,
    prompt_preview: Optional[str] = None,
    response_preview: Optional[str] = None,
):
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO requests (ts, endpoint, model, pool_account, prompt_tokens, "
            "completion_tokens, cache_tokens, success, latency_ms, error_type, "
            "chat_id, chat_title, prompt_preview, response_preview) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), endpoint, model, pool_account, prompt_tokens, completion_tokens,
             cache_tokens, 1 if success else 0, latency_ms, error_type,
             chat_id, chat_title, prompt_preview, response_preview),
        )
        if pool_account:
            conn.execute(
                "INSERT INTO pool_account_state (account_id, last_used_ts, total_requests, "
                "total_prompt_tokens, total_completion_tokens) VALUES (?, ?, 1, ?, ?) "
                "ON CONFLICT(account_id) DO UPDATE SET "
                "last_used_ts=excluded.last_used_ts, "
                "total_requests=total_requests+1, "
                "total_prompt_tokens=total_prompt_tokens+excluded.total_prompt_tokens, "
                "total_completion_tokens=total_completion_tokens+excluded.total_completion_tokens",
                (pool_account, time.time(), prompt_tokens, completion_tokens),
            )
        conn.commit()
    finally:
        conn.close()


async def record_request(
    *,
    endpoint: str,
    model: Optional[str],
    pool_account: Optional[str],
    prompt_tokens: int,
    completion_tokens: int,
    cache_tokens: int,
    success: bool,
    latency_ms: Optional[int],
    error_type: Optional[str],
    chat_id: Optional[str] = None,
    chat_title: Optional[str] = None,
    prompt_preview: Optional[str] = None,
    response_preview: Optional[str] = None,
) -> None:
    try:
        await asyncio.to_thread(
            _record_request_sync, endpoint, model, pool_account, prompt_tokens,
            completion_tokens, cache_tokens, success, latency_ms, error_type,
            chat_id, chat_title, prompt_preview, response_preview,
        )
    except Exception as e:
        logger.error(f"Failed to record stats: {e}")


def _record_availability_event_sync(event_type, reason):
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO availability_events (ts, event_type, reason) VALUES (?, ?, ?)",
            (time.time(), event_type, reason),
        )
        conn.commit()
    finally:
        conn.close()


async def record_availability_event(event_type: str, reason: Optional[str] = None) -> None:
    try:
        await asyncio.to_thread(_record_availability_event_sync, event_type, reason)
    except Exception as e:
        logger.error(f"Failed to record availability event: {e}")


# ---- summary / timeseries -----------------------------------------------------

def _get_summary_sync(window_seconds: Optional[int]) -> dict:
    conn = _conn()
    try:
        since = time.time() - window_seconds if window_seconds else 0
        totals = conn.execute(
            "SELECT COUNT(*) AS requests, "
            "SUM(success) AS success, "
            "SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failed, "
            "COALESCE(SUM(prompt_tokens),0) AS prompt_tokens, "
            "COALESCE(SUM(completion_tokens),0) AS completion_tokens, "
            "COALESCE(SUM(cache_tokens),0) AS cache_tokens "
            "FROM requests WHERE ts >= ?", (since,)
        ).fetchone()

        by_model = conn.execute(
            "SELECT model, COUNT(*) AS requests, "
            "COALESCE(SUM(prompt_tokens),0) AS prompt_tokens, "
            "COALESCE(SUM(completion_tokens),0) AS completion_tokens, "
            "COALESCE(SUM(cache_tokens),0) AS cache_tokens "
            "FROM requests WHERE ts >= ? AND model IS NOT NULL "
            "GROUP BY model ORDER BY requests DESC", (since,)
        ).fetchall()

        by_account = conn.execute(
            "SELECT pool_account, COUNT(*) AS requests, "
            "COALESCE(SUM(prompt_tokens),0) AS prompt_tokens, "
            "COALESCE(SUM(completion_tokens),0) AS completion_tokens "
            "FROM requests WHERE ts >= ? AND pool_account IS NOT NULL "
            "GROUP BY pool_account ORDER BY requests DESC", (since,)
        ).fetchall()

        recent_events = conn.execute(
            "SELECT ts, event_type, reason FROM availability_events "
            "ORDER BY ts DESC LIMIT 20"
        ).fetchall()

        return {
            "totals": {
                "requests": totals["requests"] or 0,
                "success": totals["success"] or 0,
                "failed": totals["failed"] or 0,
                "prompt_tokens": totals["prompt_tokens"] or 0,
                "completion_tokens": totals["completion_tokens"] or 0,
                "cache_tokens": totals["cache_tokens"] or 0,
                "total_tokens": request_total_tokens(
                    totals["prompt_tokens"] or 0,
                    totals["completion_tokens"] or 0,
                ),
            },
            "by_model": [dict(r) for r in by_model],
            "by_account": [dict(r) for r in by_account],
            "recent_downtime_events": [dict(r) for r in recent_events],
        }
    finally:
        conn.close()


async def get_summary(window_seconds: Optional[int] = None) -> dict:
    return await asyncio.to_thread(_get_summary_sync, window_seconds)


def _get_timeseries_sync(bucket_seconds: int, window_seconds: int) -> list:
    conn = _conn()
    try:
        since = time.time() - window_seconds
        rows = conn.execute(
            "SELECT CAST(ts / ? AS INTEGER) * ? AS bucket_start, "
            "COUNT(*) AS requests, "
            "COALESCE(SUM(prompt_tokens),0) AS prompt_tokens, "
            "COALESCE(SUM(completion_tokens),0) AS completion_tokens, "
            "COALESCE(SUM(cache_tokens),0) AS cache_tokens, "
            "SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures "
            "FROM requests WHERE ts >= ? "
            "GROUP BY bucket_start ORDER BY bucket_start ASC",
            (bucket_seconds, bucket_seconds, since),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def get_timeseries(bucket_seconds: int = 3600, window_seconds: int = 24 * 3600) -> list:
    return await asyncio.to_thread(_get_timeseries_sync, bucket_seconds, window_seconds)


# ---- chats / requests queries -------------------------------------------------

def _get_chats_grouped_sync(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    model: Optional[str] = None,
    endpoint: Optional[str] = None,
    status: Optional[str] = None,
    window_seconds: Optional[int] = None,
) -> dict:
    conn = _conn()
    try:
        conditions = []
        params = []

        if window_seconds:
            since = time.time() - window_seconds
            conditions.append("ts >= ?")
            params.append(since)

        if model:
            conditions.append("model = ?")
            params.append(model)

        if endpoint:
            conditions.append("endpoint = ?")
            params.append(endpoint)

        if status == "success":
            conditions.append("success = 1")
        elif status == "failed":
            conditions.append("success = 0")

        if search:
            term = f"%{search}%"
            conditions.append(
                "(chat_title LIKE ? OR prompt_preview LIKE ? OR response_preview LIKE ? "
                "OR chat_id LIKE ? OR model LIKE ? OR pool_account LIKE ?)"
            )
            params.extend([term, term, term, term, term, term])

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        count_sql = f"SELECT COUNT(DISTINCT COALESCE(chat_id, 'legacy_' || id)) AS cnt FROM requests {where_clause}"
        total = conn.execute(count_sql, params).fetchone()["cnt"]

        query_sql = f"""
            SELECT 
                COALESCE(chat_id, 'legacy_' || id) AS chat_id,
                COALESCE(MAX(chat_title), MAX(prompt_preview), 'Chat #' || id) AS title,
                COUNT(*) AS total_requests,
                SUM(success) AS successful_requests,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failed_requests,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(cache_tokens), 0) AS cache_tokens,
                COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS total_tokens,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                MIN(ts) AS first_ts,
                MAX(ts) AS last_ts,
                GROUP_CONCAT(DISTINCT model) AS models_str,
                GROUP_CONCAT(DISTINCT pool_account) AS accounts_str,
                GROUP_CONCAT(DISTINCT endpoint) AS endpoints_str,
                MAX(CASE WHEN success=0 THEN error_type ELSE NULL END) AS last_error
            FROM requests
            {where_clause}
            GROUP BY COALESCE(chat_id, 'legacy_' || id)
            ORDER BY last_ts DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query_sql, params + [limit, offset]).fetchall()

        chats = []
        for r in rows:
            models = [m for m in (r["models_str"] or "").split(",") if m]
            accounts = [a for a in (r["accounts_str"] or "").split(",") if a]
            endpoints = [e for e in (r["endpoints_str"] or "").split(",") if e]
            chats.append({
                "chat_id": r["chat_id"],
                "title": r["title"],
                "total_requests": r["total_requests"],
                "successful_requests": r["successful_requests"],
                "failed_requests": r["failed_requests"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "cache_tokens": r["cache_tokens"],
                "total_tokens": r["total_tokens"],
                "avg_latency_ms": int(r["avg_latency_ms"]),
                "first_ts": r["first_ts"],
                "last_ts": r["last_ts"],
                "models": models,
                "accounts": accounts,
                "endpoints": endpoints,
                "last_error": r["last_error"],
            })

        return {"total": total, "chats": chats}
    finally:
        conn.close()


async def get_chats_grouped(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    model: Optional[str] = None,
    endpoint: Optional[str] = None,
    status: Optional[str] = None,
    window_seconds: Optional[int] = None,
) -> dict:
    return await asyncio.to_thread(
        _get_chats_grouped_sync, limit, offset, search, model, endpoint, status, window_seconds
    )


def _get_chat_requests_sync(chat_id: str) -> list:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM requests "
            "WHERE chat_id = ? OR (chat_id IS NULL AND ('legacy_' || id) = ?) "
            "ORDER BY ts ASC",
            (chat_id, chat_id),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def get_chat_requests(chat_id: str) -> list:
    return await asyncio.to_thread(_get_chat_requests_sync, chat_id)


def _get_requests_list_sync(
    limit: int = 50,
    offset: int = 0,
    chat_id: Optional[str] = None,
    search: Optional[str] = None,
    model: Optional[str] = None,
    endpoint: Optional[str] = None,
    status: Optional[str] = None,
    window_seconds: Optional[int] = None,
) -> dict:
    conn = _conn()
    try:
        conditions = []
        params = []

        if chat_id:
            conditions.append("(chat_id = ? OR (chat_id IS NULL AND ('legacy_' || id) = ?))")
            params.extend([chat_id, chat_id])

        if window_seconds:
            since = time.time() - window_seconds
            conditions.append("ts >= ?")
            params.append(since)

        if model:
            conditions.append("model = ?")
            params.append(model)

        if endpoint:
            conditions.append("endpoint = ?")
            params.append(endpoint)

        if status == "success":
            conditions.append("success = 1")
        elif status == "failed":
            conditions.append("success = 0")

        if search:
            term = f"%{search}%"
            conditions.append(
                "(chat_title LIKE ? OR prompt_preview LIKE ? OR response_preview LIKE ? "
                "OR chat_id LIKE ? OR model LIKE ? OR pool_account LIKE ?)"
            )
            params.extend([term, term, term, term, term, term])

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = conn.execute(f"SELECT COUNT(*) AS cnt FROM requests {where_clause}", params).fetchone()["cnt"]

        rows = conn.execute(
            f"SELECT * FROM requests {where_clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

        return {"total": total, "requests": [dict(r) for r in rows]}
    finally:
        conn.close()


async def get_requests_list(
    limit: int = 50,
    offset: int = 0,
    chat_id: Optional[str] = None,
    search: Optional[str] = None,
    model: Optional[str] = None,
    endpoint: Optional[str] = None,
    status: Optional[str] = None,
    window_seconds: Optional[int] = None,
) -> dict:
    return await asyncio.to_thread(
        _get_requests_list_sync, limit, offset, chat_id, search, model, endpoint, status, window_seconds
    )


def _get_requests_overview_sync(window_seconds: Optional[int] = None) -> dict:
    conn = _conn()
    try:
        since = time.time() - window_seconds if window_seconds else 0
        totals = conn.execute(
            "SELECT "
            "COUNT(*) AS total_requests, "
            "COUNT(DISTINCT COALESCE(chat_id, 'legacy_' || id)) AS total_chats, "
            "COALESCE(SUM(success), 0) AS successful_requests, "
            "COALESCE(SUM(CASE WHEN success=0 THEN 1 ELSE 0 END), 0) AS failed_requests, "
            "COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens, "
            "COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens, "
            "COALESCE(SUM(cache_tokens), 0) AS total_cache_tokens, "
            "COALESCE(AVG(latency_ms), 0) AS avg_latency_ms "
            "FROM requests WHERE ts >= ?",
            (since,),
        ).fetchone()

        models = conn.execute(
            "SELECT model, COUNT(*) AS count FROM requests WHERE ts >= ? AND model IS NOT NULL GROUP BY model ORDER BY count DESC",
            (since,),
        ).fetchall()

        endpoints = conn.execute(
            "SELECT endpoint, COUNT(*) AS count FROM requests WHERE ts >= ? GROUP BY endpoint ORDER BY count DESC",
            (since,),
        ).fetchall()

        return {
            "total_requests": totals["total_requests"] or 0,
            "total_chats": totals["total_chats"] or 0,
            "successful_requests": totals["successful_requests"] or 0,
            "failed_requests": totals["failed_requests"] or 0,
            "total_prompt_tokens": totals["total_prompt_tokens"] or 0,
            "total_completion_tokens": totals["total_completion_tokens"] or 0,
            "total_cache_tokens": totals["total_cache_tokens"] or 0,
            "total_tokens": request_total_tokens(
                totals["total_prompt_tokens"] or 0,
                totals["total_completion_tokens"] or 0,
            ),
            "avg_latency_ms": int(totals["avg_latency_ms"] or 0),
            "models": [dict(m) for m in models],
            "endpoints": [dict(e) for e in endpoints],
        }
    finally:
        conn.close()


async def get_requests_overview(window_seconds: Optional[int] = None) -> dict:
    return await asyncio.to_thread(_get_requests_overview_sync, window_seconds)


def _delete_chat_sync(chat_id: str) -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM requests WHERE chat_id = ? OR (chat_id IS NULL AND ('legacy_' || id) = ?)",
            (chat_id, chat_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


async def delete_chat(chat_id: str) -> int:
    return await asyncio.to_thread(_delete_chat_sync, chat_id)


def _clear_requests_sync(window_seconds: Optional[int] = None) -> int:
    conn = _conn()
    try:
        if window_seconds:
            threshold = time.time() - window_seconds
            cur = conn.execute("DELETE FROM requests WHERE ts < ?", (threshold,))
        else:
            cur = conn.execute("DELETE FROM requests")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


async def clear_requests(window_seconds: Optional[int] = None) -> int:
    return await asyncio.to_thread(_clear_requests_sync, window_seconds)


# ---- pool account state --------------------------------------------------------

def _upsert_pool_account_state_sync(account_id: str, **fields):
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO pool_account_state (account_id) VALUES (?) "
            "ON CONFLICT(account_id) DO NOTHING", (account_id,)
        )
        if fields:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            conn.execute(
                f"UPDATE pool_account_state SET {set_clause} WHERE account_id=?",
                (*fields.values(), account_id),
            )
        conn.commit()
    finally:
        conn.close()


async def upsert_pool_account_state(account_id: str, **fields) -> None:
    await asyncio.to_thread(_upsert_pool_account_state_sync, account_id, **fields)


def _get_pool_account_state_sync(account_id: str) -> Optional[dict]:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM pool_account_state WHERE account_id=?", (account_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def get_pool_account_state(account_id: str) -> Optional[dict]:
    return await asyncio.to_thread(_get_pool_account_state_sync, account_id)


def _list_pool_account_states_sync() -> list:
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM pool_account_state").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def list_pool_account_states() -> list:
    return await asyncio.to_thread(_list_pool_account_states_sync)


def _get_active_account_id_sync() -> Optional[str]:
    conn = _conn()
    try:
        row = conn.execute("SELECT active_account_id FROM pool_runtime WHERE id=1").fetchone()
        return row["active_account_id"] if row else None
    finally:
        conn.close()


async def get_active_account_id_db() -> Optional[str]:
    return await asyncio.to_thread(_get_active_account_id_sync)


def _set_active_account_id_sync(account_id: Optional[str]):
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO pool_runtime (id, active_account_id) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET active_account_id=excluded.active_account_id",
            (account_id,),
        )
        conn.commit()
    finally:
        conn.close()


async def set_active_account_id_db(account_id: Optional[str]) -> None:
    await asyncio.to_thread(_set_active_account_id_sync, account_id)
