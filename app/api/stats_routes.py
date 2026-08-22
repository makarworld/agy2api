import time
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_api_key
from app.core import stats_store
from app.core import app_state

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats/summary", summary="Cumulative token usage, request, and uptime/downtime stats")
async def stats_summary(window_hours: Optional[int] = None, api_key: str = Depends(get_api_key)):
    window_seconds = window_hours * 3600 if window_hours else None
    summary = await stats_store.get_summary(window_seconds)
    summary["uptime_seconds"] = int(time.time() - app_state.START_TIME)
    summary["app_start_ts"] = app_state.START_TIME
    return summary


@router.get("/stats/timeseries", summary="Bucketed token usage history for charting")
async def stats_timeseries(bucket_seconds: int = 3600, window_hours: int = 24, api_key: str = Depends(get_api_key)):
    data = await stats_store.get_timeseries(bucket_seconds=bucket_seconds, window_seconds=window_hours * 3600)
    return {"bucket_seconds": bucket_seconds, "window_hours": window_hours, "data": data}


@router.get("/stats/overview", summary="High-level requests and chats statistics")
async def stats_overview(window_hours: Optional[int] = None, api_key: str = Depends(get_api_key)):
    window_seconds = window_hours * 3600 if window_hours else None
    return await stats_store.get_requests_overview(window_seconds)


@router.get("/stats/chats", summary="List chat sessions with aggregated stats and request counts")
async def list_chats(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    model: Optional[str] = None,
    endpoint: Optional[str] = None,
    status: Optional[str] = None,
    window_hours: Optional[int] = None,
    api_key: str = Depends(get_api_key),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    window_seconds = window_hours * 3600 if window_hours else None
    return await stats_store.get_chats_grouped(
        limit=limit,
        offset=offset,
        search=search.strip() if search else None,
        model=model.strip() if model else None,
        endpoint=endpoint.strip() if endpoint else None,
        status=status.strip().lower() if status else None,
        window_seconds=window_seconds,
    )


@router.get("/stats/chats/{chat_id}", summary="Get all requests belonging to a specific chat session")
async def get_chat(chat_id: str, api_key: str = Depends(get_api_key)):
    requests = await stats_store.get_chat_requests(chat_id)
    if not requests:
        raise HTTPException(status_code=404, detail=f"No requests found for chat '{chat_id}'")
    return {"chat_id": chat_id, "requests": requests}


@router.delete("/stats/chats/{chat_id}", summary="Delete a chat session and its recorded requests")
async def delete_chat_session(chat_id: str, api_key: str = Depends(get_api_key)):
    deleted_count = await stats_store.delete_chat(chat_id)
    return {"status": "ok", "chat_id": chat_id, "deleted_count": deleted_count}


@router.get("/stats/requests", summary="List raw requests with filtering and pagination")
async def list_requests(
    limit: int = 50,
    offset: int = 0,
    chat_id: Optional[str] = None,
    search: Optional[str] = None,
    model: Optional[str] = None,
    endpoint: Optional[str] = None,
    status: Optional[str] = None,
    window_hours: Optional[int] = None,
    api_key: str = Depends(get_api_key),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    window_seconds = window_hours * 3600 if window_hours else None
    return await stats_store.get_requests_list(
        limit=limit,
        offset=offset,
        chat_id=chat_id.strip() if chat_id else None,
        search=search.strip() if search else None,
        model=model.strip() if model else None,
        endpoint=endpoint.strip() if endpoint else None,
        status=status.strip().lower() if status else None,
        window_seconds=window_seconds,
    )


@router.delete("/stats/requests", summary="Clear requests history")
async def clear_requests_history(older_than_hours: Optional[int] = None, api_key: str = Depends(get_api_key)):
    window_seconds = older_than_hours * 3600 if older_than_hours else None
    deleted_count = await stats_store.clear_requests(window_seconds)
    return {"status": "ok", "deleted_count": deleted_count}
