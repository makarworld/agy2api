import os
import time
import shutil
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as api_router
from app.core.model_manager import get_available_models

import uuid
import logging
from app.core.logging_setup import setup_logging, trace_id_var

setup_logging()
logger = logging.getLogger(__name__)

async def agy_garbage_collector():
    brain_dir = os.path.expanduser("~/.gemini/antigravity-cli/brain")
    max_age_seconds = 24 * 3600  # 24 hours
    
    while True:
        try:
            if os.path.exists(brain_dir):
                now = time.time()
                for folder in os.listdir(brain_dir):
                    folder_path = os.path.join(brain_dir, folder)
                    if os.path.isdir(folder_path):
                        if now - os.path.getmtime(folder_path) > max_age_seconds:
                            shutil.rmtree(folder_path, ignore_errors=True)
                            print(f"[Garbage Collector] Deleted old conversation log: {folder}")
        except Exception as e:
            print(f"[Garbage Collector] Error cleaning up: {e}")
            
        await asyncio.sleep(6 * 3600)  # Sleep for 6 hours

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(agy_garbage_collector())
    model_warmup = asyncio.create_task(get_available_models())
    yield
    task.cancel()
    model_warmup.cancel()

app = FastAPI(
    title="AGY OpenAI API Wrapper",
    description="An OpenAI compatible API wrapper for Antigravity CLI",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(api_router, prefix="/v1")

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
ui_dist = os.path.join(os.path.dirname(__file__), "..", "ui", "dist")
if os.path.exists(ui_dist):
    app.mount("/", StaticFiles(directory=ui_dist, html=True), name="static")


