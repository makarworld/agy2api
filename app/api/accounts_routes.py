import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_api_key
from app.core import pool_manager
from app.core import stats_store

logger = logging.getLogger(__name__)

router = APIRouter()


class AddAccountRequest(BaseModel):
    label: str
    proxy: Optional[str] = None  # e.g. http://user:pass@host:port or socks5://host:port


class SetProxyRequest(BaseModel):
    proxy: Optional[str] = None  # None/empty clears the proxy


class AddFlowStartRequest(BaseModel):
    proxy: Optional[str] = None


def _pool_disabled_response():
    raise HTTPException(status_code=400, detail="Account pool is disabled (set AGY_POOL_ENABLED=true)")


@router.get("/accounts", summary="List pool accounts and their health/quota status")
async def list_accounts(api_key: str = Depends(get_api_key)):
    accounts = pool_manager.list_accounts()
    states = {s["account_id"]: s for s in await stats_store.list_pool_account_states()}
    active_id = pool_manager.get_active_account_id()

    result = []
    for acc in accounts:
        state = states.get(acc["id"], {})
        result.append({
            "id": acc["id"],
            "label": acc.get("label"),
            "added_at": acc.get("added_at"),
            "proxy": acc.get("proxy"),
            "active": acc["id"] == active_id,
            "status": state.get("status", "healthy"),
            "cooldown_until": state.get("cooldown_until"),
            "consecutive_failures": state.get("consecutive_failures", 0),
            "last_used_ts": state.get("last_used_ts"),
            "total_requests": state.get("total_requests", 0),
            "total_prompt_tokens": state.get("total_prompt_tokens", 0),
            "total_completion_tokens": state.get("total_completion_tokens", 0),
        })
    return {"pool_enabled": pool_manager.pool_enabled(), "accounts": result}


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
