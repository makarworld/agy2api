import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core import key_manager
from app.core.security import require_master_key

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateKeyRequest(BaseModel):
    name: str = Field(..., description="Descriptive name for the key")
    expires_in_days: int | None = Field(
        None, description="Expiration in days (optional)"
    )
    daily_output_limit: int | None = Field(
        None, description="Daily output token limit (optional)"
    )


class UpdateKeyRequest(BaseModel):
    is_active: bool | None = Field(None, description="Active status")


@router.get("/admin/keys", summary="List all API keys (Master key required)")
async def list_keys(_master: str = Depends(require_master_key)):
    keys = key_manager.list_keys()
    return {"keys": keys}


@router.post("/admin/keys", summary="Create a new API key (Master key required)")
async def create_key(req: CreateKeyRequest, _master: str = Depends(require_master_key)):
    if not req.name or not req.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Key name is required",
        )
    key_info = key_manager.create_key(
        name=req.name,
        expires_in_days=req.expires_in_days,
        daily_output_limit=req.daily_output_limit,
    )
    return {"status": "ok", "key": key_info.to_dict()}


@router.delete(
    "/admin/keys/{key_id:path}", summary="Delete an API key (Master key required)"
)
async def delete_key(key_id: str, _master: str = Depends(require_master_key)):
    deleted = key_manager.delete_key(key_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    return {"status": "ok", "deleted": key_id}


@router.patch(
    "/admin/keys/{key_id:path}",
    summary="Toggle or update API key status (Master key required)",
)
async def update_key(
    key_id: str,
    req: UpdateKeyRequest | None = None,
    _master: str = Depends(require_master_key),
):
    is_active = req.is_active if req is not None else None
    updated = key_manager.toggle_key(key_id, is_active=is_active)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    return {"status": "ok", "key": updated}
