"""Centralized filesystem paths for AGY2API.

Ensures all application data (SQLite DBs, account pools, logs, .env config)
is stored consistently in a single user home directory across platforms:
- Windows: C:\\Users\\<User>\\.agy2api\\
- Linux / macOS: ~/.agy2api/ (/home/<user>/.agy2api/)
"""

import os
import sys


def get_agy_home() -> str:
    """Root user directory for all AGY2API persistent files."""
    custom = os.environ.get("AGY_HOME")
    if custom and custom.strip():
        return os.path.abspath(os.path.expanduser(custom.strip()))
    return os.path.abspath(os.path.expanduser("~/.agy2api"))


def get_data_dir() -> str:
    """Directory for SQLite databases and accounts data."""
    custom = os.environ.get("AGY_DATA_DIR")
    if custom and custom.strip():
        return os.path.abspath(os.path.expanduser(custom.strip()))
    return os.path.join(get_agy_home(), "data")


def get_db_path() -> str:
    """Path to the main SQLite database (stats, accounts, requests)."""
    custom = os.environ.get("AGY_DB_PATH") or os.environ.get("AGY_STATS_DB_PATH")
    if custom and custom.strip():
        return os.path.abspath(os.path.expanduser(custom.strip()))
    return os.path.join(get_data_dir(), "stats.db")


def get_accounts_json_path() -> str:
    """Path to legacy/sync accounts.json file."""
    custom = os.environ.get("ACCOUNTS_FILE")
    if custom and custom.strip():
        return os.path.abspath(os.path.expanduser(custom.strip()))
    return os.path.join(get_data_dir(), "accounts.json")


def get_log_file_path() -> str:
    """Path to the rotating application log file."""
    custom = os.environ.get("AGY_LOG_FILE_PATH")
    if custom and custom.strip():
        return os.path.abspath(os.path.expanduser(custom.strip()))
    return os.path.join(get_agy_home(), "agy2api.log")


def get_pool_dir() -> str:
    """Directory holding account snapshots and credential pools.

    Prioritizes AGY_POOL_DIR, then ~/.agy2api/pool.
    Falls back to legacy ~/.agy2api-pool if that directory already exists.
    """
    custom = os.environ.get("AGY_POOL_DIR")
    if custom and custom.strip():
        return os.path.abspath(os.path.expanduser(custom.strip()))

    legacy_pool = os.path.abspath(os.path.expanduser("~/.agy2api-pool"))
    standard_pool = os.path.join(get_agy_home(), "pool")

    if os.path.exists(legacy_pool) and not os.path.exists(standard_pool):
        return legacy_pool

    return standard_pool


def get_env_file_path() -> str:
    """Path to the runtime .env configuration file."""
    custom = os.environ.get("AGY_ENV_FILE")
    if custom and custom.strip():
        return os.path.abspath(os.path.expanduser(custom.strip()))

    home_env = os.path.join(get_agy_home(), ".env")
    if os.path.exists(home_env):
        return home_env

    # In dev mode, check repository root
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    repo_env = os.path.join(repo_root, ".env")
    if not getattr(sys, "frozen", False) and os.path.exists(repo_env):
        return repo_env

    return home_env


def ensure_agy_dirs() -> None:
    """Create all required user directories if they do not exist."""
    os.makedirs(get_agy_home(), exist_ok=True)
    os.makedirs(get_data_dir(), exist_ok=True)
    os.makedirs(get_pool_dir(), exist_ok=True)
