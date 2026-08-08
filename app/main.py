import os
import time
import shutil
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as api_router

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
    yield
    task.cancel()

app = FastAPI(
    title="AGY OpenAI API Wrapper",
    description="An OpenAI compatible API wrapper for Antigravity CLI",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(api_router, prefix="/v1")

@app.get("/health")
async def health_check():
    return JSONResponse(content={"status": "ok", "message": "AGY wrapper is running"})

# Serve UI if dist folder exists
ui_dist = os.path.join(os.path.dirname(__file__), "..", "ui", "dist")
if os.path.exists(ui_dist):
    app.mount("/", StaticFiles(directory=ui_dist, html=True), name="static")


