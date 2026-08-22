"""
CLI helper to add the currently logged-in `agy` session as a new account in
the local account pool.

Usage:
    1. Run `agy auth login` for the account you want to add and complete the
       browser OAuth flow.
    2. Run this script: `python scripts/add_account_to_pool.py`
    3. Commit and push the pool directory (AGY_POOL_DIR, default
       ~/.agy2api-pool) to your private GitHub repo, or call
       POST /v1/accounts/sync?push=true on a running server.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import pool_manager  # noqa: E402


async def main():
    print("This snapshots the CURRENTLY logged-in agy session (~/.gemini) as a new pool account.")
    print("Make sure you already ran `agy auth login` for the account you want to add.\n")
    label = input("Label for this account (e.g. 'personal-gmail'): ").strip()
    if not label:
        print("Label cannot be empty.")
        return
    proxy = input("Proxy for this account (optional, e.g. http://user:pass@host:port, Enter to skip): ").strip() or None

    pool_dir = pool_manager._pool_dir()
    if not os.path.isdir(os.path.join(pool_dir, ".git")):
        print(f"Note: {pool_dir} is not a git repo yet.")
        print(f"Run: git init {pool_dir}  (or clone your private pool repo to that path)")

    try:
        record = await pool_manager.snapshot_current_session_to_account(label, proxy=proxy)
    except RuntimeError as e:
        print(f"Failed: {e}")
        return

    print(f"\nAdded account: {record['id']} ({record['label']})")
    print(f"Pool directory: {pool_dir}")
    print("Next: commit and push the pool directory, e.g.:")
    print(f"  git -C {pool_dir} add -A && git -C {pool_dir} commit -m 'Add {record['id']}' && git -C {pool_dir} push")
    print("Or call: POST /v1/accounts/sync?push=true")


if __name__ == "__main__":
    asyncio.run(main())
