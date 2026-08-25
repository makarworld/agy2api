import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_api_key
from app.core import pool_manager
from app.core import stats_store
from app.core import oauth_refresh

logger = logging.getLogger(__name__)

router = APIRouter()


class AddAccountRequest(BaseModel):
    label: str
    proxy: Optional[str] = None  # e.g. http://user:pass@host:port or socks5://host:port


class SetProxyRequest(BaseModel):
    proxy: Optional[str] = None  # None/empty clears the proxy


class AddFlowStartRequest(BaseModel):
    proxy: Optional[str] = None


class OAuthCompleteRequest(BaseModel):
    flow_id: Optional[str] = None
    code: str
    label: Optional[str] = None
    proxy: Optional[str] = None
    code_verifier: Optional[str] = None


def _pool_disabled_response():
    raise HTTPException(status_code=400, detail="Account pool is disabled (set AGY_POOL_ENABLED=true)")


@router.get("/accounts", summary="List pool accounts and their health/quota status")
async def list_accounts(api_key: str = Depends(get_api_key)):
    accounts = pool_manager.list_accounts()
    states = {s["account_id"]: s for s in await stats_store.list_pool_account_states()}
    active_id = pool_manager.get_active_account_id()

    # If pool is disabled, we still might have the active session in accounts or single account
    account_items = (
        accounts if pool_manager.pool_enabled() else (accounts or [{"id": "active", "label": "Default Session"}])
    )

    result = []
    for acc in account_items:
        acc_id = acc.get("id", "active")
        state = states.get(acc_id, {})
        token, proxy, account_dir = pool_manager.get_account_token_and_proxy(acc_id)
        quota_data = {}
        if token or account_dir:
            try:
                quota_data = await oauth_refresh.retrieve_account_quota(
                    account_dir=account_dir,
                    access_token=token,
                    proxy=proxy,
                    pool_account_id=acc_id,
                )
            except Exception as e:
                logger.debug(f"[accounts] Failed to retrieve quota for {acc_id}: {e}")

        result.append(
            {
                "id": acc_id,
                "label": acc.get("label"),
                "email": acc.get("email"),
                "added_at": acc.get("added_at"),
                "proxy": acc.get("proxy"),
                "active": acc_id == active_id if pool_manager.pool_enabled() else True,
                "status": state.get("status", "healthy"),
                "cooldown_until": state.get("cooldown_until"),
                "consecutive_failures": state.get("consecutive_failures", 0),
                "last_used_ts": state.get("last_used_ts"),
                "total_requests": state.get("total_requests", 0),
                "total_prompt_tokens": state.get("total_prompt_tokens", 0),
                "total_completion_tokens": state.get("total_completion_tokens", 0),
                "quota": quota_data,
            }
        )
    return {"pool_enabled": pool_manager.pool_enabled(), "accounts": result}


@router.get("/accounts/oauth/start", summary="Generate Antigravity Google OAuth PKCE authorization URL")
async def start_oauth_flow(proxy: Optional[str] = None, api_key: str = Depends(get_api_key)):
    return pool_manager.generate_oauth_auth_url(proxy=proxy)


@router.post("/accounts/oauth/complete", summary="Exchange Google OAuth code for tokens and save account to pool")
async def complete_oauth_flow_route(req: OAuthCompleteRequest, api_key: str = Depends(get_api_key)):
    try:
        record = await pool_manager.complete_oauth_flow(
            flow_id=req.flow_id,
            code=req.code,
            label=req.label,
            proxy=req.proxy,
            code_verifier=req.code_verifier,
        )
        return record
    except Exception as e:
        logger.error(f"[accounts] OAuth completion failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/accounts", summary="Snapshot the currently logged-in agy session as a new pool account")
async def add_account(req: AddAccountRequest, api_key: str = Depends(get_api_key)):
    try:
        record = await pool_manager.snapshot_current_session_to_account(req.label, proxy=req.proxy)
        return record
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/accounts/add-flow/start", summary="Start adding a new pool account (opens a login terminal)")
async def start_add_flow(req: AddFlowStartRequest, api_key: str = Depends(get_api_key)):
    return await pool_manager.start_add_account_flow(proxy=req.proxy)


@router.get("/accounts/add-flow/status", summary="Check whether a new login session was detected")
async def add_flow_status(api_key: str = Depends(get_api_key)):
    return await pool_manager.check_add_account_flow()


@router.post("/accounts/add-flow/cancel", summary="Cancel the pending add-account flow")
async def cancel_add_flow(api_key: str = Depends(get_api_key)):
    pool_manager.cancel_add_account_flow()
    return {"cancelled": True}


@router.put("/accounts/{account_id}/proxy", summary="Attach or clear a proxy for this account")
async def set_account_proxy(account_id: str, req: SetProxyRequest, api_key: str = Depends(get_api_key)):
    try:
        return pool_manager.set_account_proxy(account_id, req.proxy)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/accounts/{account_id}/activate", summary="Manually switch the active agy account")
async def activate_account(account_id: str, api_key: str = Depends(get_api_key)):
    try:
        await pool_manager.activate_account(account_id)
        return {"active_account_id": account_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/accounts/{account_id}", summary="Remove an account from the pool")
async def delete_account(account_id: str, api_key: str = Depends(get_api_key)):
    await pool_manager.delete_account(account_id)
    return {"deleted": account_id}


@router.post("/accounts/sync", summary="Sync the account pool with its git remote")
async def sync_accounts(push: bool = False, api_key: str = Depends(get_api_key)):
    try:
        pull_out = await pool_manager.git_pull()
        push_out = None
        if push:
            push_out = await pool_manager.git_commit_and_push()
        return {"pull": pull_out, "push": push_out}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
