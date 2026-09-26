import os
import sqlite3

from app.core.paths import get_data_dir, get_db_path as _get_default_db_path

DATA_DIR = get_data_dir()
DB_PATH = _get_default_db_path()


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
