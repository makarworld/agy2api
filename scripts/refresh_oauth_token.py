"""
Refresh OAuth access_token via Google token endpoint and write to disk.

Usage:
    python scripts/refresh_oauth_token.py
    python scripts/refresh_oauth_token.py --file ~/.gemini/oauth_creds.json
    python scripts/refresh_oauth_token.py --sync-pool

Requires ANTIGRAVITY_CLIENT_ID and ANTIGRAVITY_CLIENT_SECRET in .env or environment.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import oauth_refresh  # noqa: E402
from app.core import pool_manager  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh OAuth credentials on disk")
    parser.add_argument(
        "--file",
        dest="path",
        default=None,
        help="Credential file path (default: auto-discover under ~/.gemini)",
    )
    parser.add_argument(
        "--sync-pool",
        action="store_true",
        help="Sync refreshed credentials back to active pool account snapshot",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refresh even when expiry looks valid",
    )
    args = parser.parse_args()

    home = os.path.expanduser("~/.gemini")
    proxy = pool_manager.get_active_account_proxy() if pool_manager.pool_enabled() else None

    if args.path:
        kind = oauth_refresh.credential_kind_for_path(args.path)
        oauth_refresh._set_active_credential(args.path, kind)

    refreshed = await oauth_refresh.ensure_fresh_credentials(
        home,
        proxy=proxy,
        pool_account_id=pool_manager.get_active_account_id(),
        force=args.force,
    )
    if not refreshed:
        token = oauth_refresh.read_access_token(home)
        suffix = oauth_refresh._token_suffix(token)
        ok = await oauth_refresh.verify_access_token(token, proxy=proxy)
        if ok:
            print(f"No refresh needed — access token still valid (suffix {suffix})")
        else:
            print("Refresh skipped or failed — check logs and credential file", file=sys.stderr)
            sys.exit(1)
    else:
        token = oauth_refresh.read_access_token(home)
        suffix = oauth_refresh._token_suffix(token)
        print(f"Refreshed access token (suffix {suffix})")

    ok = await oauth_refresh.verify_access_token(token, proxy=proxy)
    if ok:
        print("quota verify OK")
    else:
        print("quota verify FAILED after refresh", file=sys.stderr)
        sys.exit(1)

    if args.sync_pool and pool_manager.pool_enabled():
        account_id = pool_manager.get_active_account_id()
        if account_id:
            await pool_manager.sync_back_credentials(account_id)
            print(f"Synced credentials to pool account {account_id}")
        else:
            print("No active pool account — skip sync")


if __name__ == "__main__":
    asyncio.run(main())
