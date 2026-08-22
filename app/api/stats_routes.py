import time
import logging

from fastapi import APIRouter, Depends

from app.core.security import get_api_key
from app.core import stats_store
from app.core import app_state

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats/summary", summary="Cumulative token usage, request, and uptime/downtime stats")
async def stats_summary(window_hours: int = None, api_key: str = Depends(get_api_key)):
    window_seconds = window_hours * 3600 if window_hours else None
    summary = await stats_store.get_summary(window_seconds)
    summary["uptime_seconds"] = int(time.time() - app_state.START_TIME)
    summary["app_start_ts"] = app_state.START_TIME
    return summary


@router.get("/stats/timeseries", summary="Bucketed token usage history for charting")
async def stats_timeseries(bucket_seconds: int = 3600, window_hours: int = 24, api_key: str = Depends(get_api_key)):
    data = await stats_store.get_timeseries(bucket_seconds=bucket_seconds, window_seconds=window_hours * 3600)
    return {"bucket_seconds": bucket_seconds, "window_hours": window_hours, "data": data}
