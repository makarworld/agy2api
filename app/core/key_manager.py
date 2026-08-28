import os
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.core import stats_store

_KEYS_DDL = """
CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    expires_at REAL,
    daily_output_limit INTEGER,
    used_output_today INTEGER NOT NULL DEFAULT 0,
    last_reset_day TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);
"""


@dataclass
class KeyInfo:
    key: str
    name: str
    is_active: bool = True
    is_master: bool = False
    created_at: float = 0.0
    expires_at: float | None = None
    daily_output_limit: int | None = None
    used_output_today: int = 0
    last_reset_day: str | None = None

    def __str__(self) -> str:
        return self.key

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def init_keys_db(conn: sqlite3.Connection | None = None) -> None:
    should_close = False
    if conn is None:
        conn = stats_store._conn()
        should_close = True
    try:
        conn.executescript(_KEYS_DDL)
        conn.commit()
    finally:
        if should_close:
            conn.close()


def _get_master_keys() -> set[str]:
    keys = {"sk-dummy"}
    for env_var in (
        "AGY_API_KEY",
        "ADMIN_PASSWORD",
        "AGY_ADMIN_PASSWORD",
        "ANTHROPIC_COMPAT_API_KEY",
    ):
        val = os.environ.get(env_var)
        if val and val.strip():
            keys.add(val.strip())
    return keys


def is_master_key(key: str) -> bool:
    if not key:
        return False
    return key.strip() in _get_master_keys()


def create_key(
    name: str,
    expires_in_days: int | None = None,
    daily_output_limit: int | None = None,
) -> KeyInfo:
    init_keys_db()
    key_str = f"sk-agy-{secrets.token_urlsafe(24)}"
    now = time.time()
    expires_at = (
        now + (expires_in_days * 86400)
        if (expires_in_days is not None and expires_in_days > 0)
        else None
    )
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    limit = (
        int(daily_output_limit)
        if (daily_output_limit is not None and daily_output_limit > 0)
        else None
    )

    conn = stats_store._conn()
    try:
        conn.execute(
            "INSERT INTO api_keys (key, name, is_active, created_at, expires_at, daily_output_limit, used_output_today, last_reset_day) "
            "VALUES (?, ?, 1, ?, ?, ?, 0, ?)",
            (key_str, name.strip(), now, expires_at, limit, today_utc),
        )
        conn.commit()
    finally:
        conn.close()

    return KeyInfo(
        key=key_str,
        name=name.strip(),
        is_active=True,
        is_master=False,
        created_at=now,
        expires_at=expires_at,
        daily_output_limit=limit,
        used_output_today=0,
        last_reset_day=today_utc,
    )


def list_keys() -> list[dict[str, Any]]:
    init_keys_db()
    conn = stats_store._conn()
    try:
        rows = conn.execute(
            "SELECT * FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result = []
        for r in rows:
            d = dict(r)
            d["is_active"] = bool(d["is_active"])
            if d.get("last_reset_day") != today_utc:
                d["used_output_today"] = 0
            result.append(d)
        return result
    finally:
        conn.close()


def delete_key(key: str) -> bool:
    init_keys_db()
    conn = stats_store._conn()
    try:
        cur = conn.execute("DELETE FROM api_keys WHERE key = ?", (key,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def toggle_key(key: str, is_active: bool | None = None) -> dict[str, Any] | None:
    init_keys_db()
    conn = stats_store._conn()
    try:
        row = conn.execute("SELECT * FROM api_keys WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        new_status = (
            (1 if is_active else 0)
            if is_active is not None
            else (0 if row["is_active"] else 1)
        )
        conn.execute(
            "UPDATE api_keys SET is_active = ? WHERE key = ?", (new_status, key)
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM api_keys WHERE key = ?", (key,)
        ).fetchone()
        if updated:
            d = dict(updated)
            d["is_active"] = bool(d["is_active"])
            return d
        return None
    finally:
        conn.close()


def validate_and_consume_key(key: str | None) -> KeyInfo:
    if not key or not str(key).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clean_key = str(key).strip()

    if is_master_key(clean_key):
        return KeyInfo(
            key=clean_key,
            name="Master Key",
            is_active=True,
            is_master=True,
        )

    init_keys_db()
    conn = stats_store._conn()
    try:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key = ?", (clean_key,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not bool(row["is_active"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key is deactivated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        now_ts = time.time()
        if row["expires_at"] is not None and now_ts > row["expires_at"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        used_today = row["used_output_today"] or 0
        last_day = row["last_reset_day"]

        if last_day != today_utc:
            used_today = 0
            conn.execute(
                "UPDATE api_keys SET used_output_today = 0, last_reset_day = ? WHERE key = ?",
                (today_utc, clean_key),
            )
            conn.commit()

        daily_limit = row["daily_output_limit"]
        if daily_limit is not None and daily_limit > 0 and used_today >= daily_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily output token limit of {daily_limit} exceeded (used: {used_today})",
            )

        return KeyInfo(
            key=row["key"],
            name=row["name"],
            is_active=bool(row["is_active"]),
            is_master=False,
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            daily_output_limit=row["daily_output_limit"],
            used_output_today=used_today,
            last_reset_day=today_utc,
        )
    finally:
        conn.close()


def record_key_output_tokens(key: str | None, output_tokens: int) -> None:
    if not key or output_tokens <= 0:
        return
    clean_key = str(key).strip()
    if is_master_key(clean_key):
        return

    init_keys_db()
    conn = stats_store._conn()
    try:
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT used_output_today, last_reset_day FROM api_keys WHERE key = ?",
            (clean_key,),
        ).fetchone()
        if not row:
            return

        if row["last_reset_day"] != today_utc:
            conn.execute(
                "UPDATE api_keys SET used_output_today = ?, last_reset_day = ? WHERE key = ?",
                (output_tokens, today_utc, clean_key),
            )
        else:
            conn.execute(
                "UPDATE api_keys SET used_output_today = used_output_today + ? WHERE key = ?",
                (output_tokens, clean_key),
            )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
