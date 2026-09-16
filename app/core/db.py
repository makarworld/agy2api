import os
import sqlite3

_DEFAULT_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
DATA_DIR = os.environ.get("AGY_DATA_DIR", _DEFAULT_DATA_DIR)
DB_PATH = os.environ.get(
    "AGY_DB_PATH",
    os.environ.get("AGY_STATS_DB_PATH", os.path.join(DATA_DIR, "stats.db")),
)


def set_db_path(path: str) -> None:
    global DB_PATH
    DB_PATH = path


def get_db_path() -> str:
    return DB_PATH


def get_connection(db_path: str | None = None, timeout: float = 30.0) -> sqlite3.Connection:
    target = db_path or DB_PATH
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    conn = sqlite3.connect(target, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn
