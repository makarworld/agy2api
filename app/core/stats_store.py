import asyncio
import os
import sqlite3
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

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
    error_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts);
CREATE INDEX IF NOT EXISTS idx_requests_account ON requests(pool_account);
CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model);

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
        conn.commit()
    finally:
        conn.close()
    logger.info(f"Stats DB initialized at {_DB_PATH}")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---- requests / availability -------------------------------------------------

def _record_request_sync(endpoint, model, pool_account, prompt_tokens, completion_tokens,
                          cache_tokens, success, latency_ms, error_type):
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO requests (ts, endpoint, model, pool_account, prompt_tokens, "
            "completion_tokens, cache_tokens, success, latency_ms, error_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), endpoint, model, pool_account, prompt_tokens, completion_tokens,
             cache_tokens, 1 if success else 0, latency_ms, error_type),
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


async def record_request(*, endpoint: str, model: Optional[str], pool_account: Optional[str],
                          prompt_tokens: int, completion_tokens: int, cache_tokens: int,
                          success: bool, latency_ms: Optional[int], error_type: Optional[str]) -> None:
    try:
        await asyncio.to_thread(
            _record_request_sync, endpoint, model, pool_account, prompt_tokens,
            completion_tokens, cache_tokens, success, latency_ms, error_type,
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
