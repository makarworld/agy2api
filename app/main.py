from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as api_router
import os

app = FastAPI(
    title="AGY OpenAI API Wrapper",
    description="An OpenAI compatible API wrapper for Antigravity CLI",
    version="1.0.0"
)

app.include_router(api_router, prefix="/v1")

@app.get("/health")
async def health_check():
    return JSONResponse(content={"status": "ok", "message": "AGY wrapper is running"})

# Serve UI if dist folder exists
ui_dist = os.path.join(os.path.dirname(__file__), "..", "ui", "dist")
if os.path.exists(ui_dist):
    app.mount("/", StaticFiles(directory=ui_dist, html=True), name="static")


