import asyncio
import logging
import os
import shutil
import sys
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.accounts_routes import router as accounts_router
from app.api.anthropic_routes import router as anthropic_router
from app.api.keys_routes import router as keys_router
from app.api.mcp_routes import router as mcp_router
from app.api.routes import router as api_router
from app.api.settings_routes import router as settings_router
from app.api.stats_routes import router as stats_router
from app.core import agy_session_pool, pool_manager, stats_store
from app.core.logging_setup import setup_logging, trace_id_var
from app.core.model_manager import get_available_models

setup_logging()
logger = logging.getLogger(__name__)


async def agy_garbage_collector():
    brain_dir = os.path.expanduser("~/.gemini/antigravity-cli/brain")
    max_age_seconds = 24 * 3600  # 24 hours
    stats_retention_seconds = int(os.environ.get("AGY_STATS_TEXT_RETENTION_SECONDS", 30 * 86400))

    while True:
        try:
            # 1. Clean old disk brain logs
            if os.path.exists(brain_dir):
                now = time.time()
                for folder in os.listdir(brain_dir):
                    folder_path = os.path.join(brain_dir, folder)
                    if os.path.isdir(folder_path) and now - os.path.getmtime(folder_path) > max_age_seconds:
                        shutil.rmtree(folder_path, ignore_errors=True)
                        print(f"[Garbage Collector] Deleted old conversation log: {folder}")
            # 2. Prune old prompt/response text in stats DB (> 30 days), preserving count/tokens/status/errors
            await stats_store.prune_old_request_previews(stats_retention_seconds)
        except Exception as e:
            print(f"[Garbage Collector] Error cleaning up: {e}")

        await asyncio.sleep(6 * 3600)  # Sleep for 6 hours


async def pool_git_autosync_loop():
    interval = int(os.environ.get("AGY_POOL_GIT_AUTOSYNC_INTERVAL_SECONDS", "3600"))
    while True:
        await asyncio.sleep(interval)
        try:
            await pool_manager.git_pull()
            print("[Pool Autosync] Pulled latest account pool state")
        except Exception as e:
            print(f"[Pool Autosync] Error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    stats_store.init_db(os.environ.get("AGY_STATS_DB_PATH", "app/data/stats.db"))
    await pool_manager.init_pool_state()

    task = asyncio.create_task(agy_garbage_collector())
    model_warmup = asyncio.create_task(get_available_models())
    autosync_task = None
    if os.environ.get("AGY_POOL_GIT_AUTOSYNC", "false").strip().lower() == "true":
        autosync_task = asyncio.create_task(pool_git_autosync_loop())

    yield

    task.cancel()
    model_warmup.cancel()
    if autosync_task:
        autosync_task.cancel()
    await agy_session_pool.shutdown()


app = FastAPI(
    title="AGY OpenAI API Wrapper",
    description="An OpenAI compatible API wrapper for Antigravity CLI",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/v1")
app.include_router(api_router, prefix="/openai/v1")
app.include_router(anthropic_router, prefix="/anthropic/v1")
app.include_router(stats_router, prefix="/v1")
app.include_router(accounts_router, prefix="/v1")
app.include_router(settings_router, prefix="/v1")
app.include_router(keys_router, prefix="/v1")
app.include_router(mcp_router)


@app.exception_handler(HTTPException)
async def anthropic_style_http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/anthropic/"):
        error_type = "authentication_error" if exc.status_code == 401 else "invalid_request_error"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": "error",
                "error": {"type": error_type, "message": exc.detail},
            },
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.middleware("http")
async def trace_log_middleware(request: Request, call_next):
    trace_id = uuid.uuid4().hex[:8]
    trace_id_var.set(trace_id)

    logger.info(f"Incoming request: {request.method} {request.url.path}")
    start_time = time.time()

    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"Completed request: {response.status_code} in {process_time:.3f}s")
        response.headers["X-Trace-ID"] = trace_id
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Request failed: {str(e)} in {process_time:.3f}s", exc_info=True)
        raise


@app.get("/health")
async def health_check():
    return JSONResponse(content={"status": "ok", "message": "AGY wrapper is running"})


# Serve UI if dist folder exists
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ui_candidates = [
    os.path.join(base_dir, "ui", "dist"),
    os.path.join(base_dir, "dist"),
    os.path.join(os.path.dirname(__file__), "..", "ui", "dist"),
    "/app/ui/dist",
]
ui_dist = next((p for p in ui_candidates if os.path.exists(p)), ui_candidates[0])


@app.get("/")
async def root_index():
    index_path = os.path.join(ui_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"detail": f"UI not built, checked: {ui_candidates}"})


@app.exception_handler(404)
async def spa_fallback_handler(request: Request, exc):
    # React Router routes (e.g. /stats, /pool) have no matching file on disk --
    # StaticFiles 404s on those. Serve index.html so the client-side router can
    # take over, for any GET that isn't an API call.
    if request.method == "GET" and not request.url.path.startswith(("/v1/", "/anthropic/", "/health")):
        index_path = os.path.join(ui_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


if os.path.exists(ui_dist):
    app.mount("/", StaticFiles(directory=ui_dist, html=True), name="static")
