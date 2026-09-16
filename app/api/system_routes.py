import logging
import os
import subprocess

from fastapi import APIRouter, Depends
from app.core.security import get_api_key

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/auth/verify", summary="Verify admin password / API key")
async def verify_auth(api_key: str = Depends(get_api_key)):
    return {"status": "ok", "authenticated": True}


def _read_local_log_tail(lines: int) -> str:
    log_path = os.environ.get("AGY_LOG_FILE_PATH", "app/data/agy2api.log")
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        if not all_lines:
            return "Log file is empty."
        return "".join(all_lines[-lines:])
    except FileNotFoundError:
        return "No log file found yet."


@router.get(
    "/logs",
    summary="Get System Logs",
    description="Read the latest system logs of the AGY Wrapper service.",
)
async def get_logs(lines: int = 100, api_key: str = Depends(get_api_key)):
    try:
        result = subprocess.run(
            [
                "journalctl",
                "--user",
                "-u",
                "agy-wrapper.service",
                "-n",
                str(lines),
                "--no-pager",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return {"logs": result.stdout}
        return {"logs": _read_local_log_tail(lines)}
    except FileNotFoundError:
        return {"logs": _read_local_log_tail(lines)}
    except Exception as e:
        return {"logs": f"Error reading logs: {str(e)}"}
