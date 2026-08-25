"""Start uvicorn with Windows console colors enabled."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.core.logging_setup import console_colors_enabled, enable_windows_console_ansi  # noqa: E402

enable_windows_console_ansi()

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("AGY_HOST", "127.0.0.1")
    port = int(os.environ.get("AGY_PORT", "26767"))
    reload = os.environ.get("AGY_RELOAD", "").lower() in ("1", "true", "yes")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        use_colors=console_colors_enabled(),
    )
