"""Entrypoint for standalone single-file AGY2API executable (Windows & Linux)."""

import os
import sys
import webbrowser

if getattr(sys, "frozen", False):
    ROOT_DIR = sys._MEIPASS
else:
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.core.paths import ensure_agy_dirs, get_env_file_path, get_agy_home

ensure_agy_dirs()

from dotenv import load_dotenv

env_file = get_env_file_path()
if os.path.exists(env_file):
    load_dotenv(env_file)

os.environ.setdefault("AGY_HOST", "127.0.0.1")
os.environ.setdefault("AGY_PORT", "26767")
os.environ.setdefault("AGY_POOL_ENABLED", "true")
os.environ.setdefault("AGY_API_KEY", "agy-secret-key-12345")
os.environ.setdefault(
    "ANTIGRAVITY_CLIENT_ID",
    "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com",
)
os.environ.setdefault("ANTIGRAVITY_CLIENT_SECRET", "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")

from app.core.logging_setup import console_colors_enabled, enable_windows_console_ansi

enable_windows_console_ansi()

from app.main import app
import uvicorn

if __name__ == "__main__":
    host = os.environ.get("AGY_HOST", "127.0.0.1")
    port = int(os.environ.get("AGY_PORT", "26767"))
    api_key = os.environ.get("AGY_API_KEY", "agy-secret-key-12345")
    url = f"http://{host}:{port}"
    agy_home = get_agy_home()

    print("=" * 60)
    print("   AGY2API Server is running!")
    print(f"   Home dir: {agy_home}")
    print(f"   Web UI:   {url}")
    print(f"   API Key:  {api_key}")
    print(f"   OpenAI:   {url}/v1")
    print(f"   Claude:   {url}/anthropic/v1")
    print("=" * 60)
    print("Opening Web UI in your default browser...")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        use_colors=console_colors_enabled(),
    )
