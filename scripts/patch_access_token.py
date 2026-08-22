"""
Patch access_token on disk without changing refresh_token.

Usage:
    python scripts/patch_access_token.py <access_token>
    python scripts/patch_access_token.py --file ~/.gemini/oauth_creds.json <access_token>

After patching, re-snapshot the pool account if AGY_POOL_ENABLED=true:
    python scripts/add_account_to_pool.py
    # or POST /v1/accounts on a running server
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import oauth_refresh  # noqa: E402
from app.core import pool_manager  # noqa: E402


async def _verify_and_report(token: str, proxy: str | None) -> bool:
    ok = await oauth_refresh.verify_access_token(token, proxy=proxy)
    suffix = oauth_refresh._token_suffix(token)
    if ok:
        print(f"quota verify OK (suffix {suffix})")
    else:
        print(f"quota verify FAILED (suffix {suffix}) — token may be expired or wrong")
    return ok


async def main() -> None:
    parser = argparse.ArgumentParser(description="Patch OAuth access_token on disk")
    parser.add_argument("access_token", help="OAuth access token (Bearer prefix optional)")
    parser.add_argument(
        "--file",
        dest="path",
        default=None,
        help="Credential file path (default: ~/.gemini/oauth_creds.json or antigravity-oauth-token)",
    )
    parser.add_argument(
        "--expires-in",
        type=int,
        default=3600,
        help="Seconds until patched expiry (default: 3600)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify token via quota API, do not write disk",
    )
    parser.add_argument(
        "--sync-pool",
        action="store_true",
        help="Sync patched credentials back to active pool account snapshot",
    )
    args = parser.parse_args()

    token = args.access_token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    proxy = pool_manager.get_active_account_proxy() if pool_manager.pool_enabled() else None

    if args.verify_only:
        ok = await _verify_and_report(token, proxy)
        sys.exit(0 if ok else 1)

    path = oauth_refresh.patch_access_token_to_file(
        token,
        path=args.path,
        expires_in=args.expires_in,
    )
    print(f"Patched {path}")

    ok = await _verify_and_report(token, proxy)
    if not ok:
        sys.exit(1)

    if args.sync_pool and pool_manager.pool_enabled():
        account_id = pool_manager.get_active_account_id()
        if account_id:
            await pool_manager.sync_back_credentials(account_id)
            print(f"Synced credentials to pool account {account_id}")
        else:
            print("No active pool account — skip sync (activate an account or use add_account_to_pool.py)")


if __name__ == "__main__":
    asyncio.run(main())
