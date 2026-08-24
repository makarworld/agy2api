import os
import sys
import uvicorn
from dotenv import load_dotenv

# Base directory
if getattr(sys, "frozen", False):
    # Running inside PyInstaller bundle
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

# Load .env from same directory as executable / script
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
else:
    # Try current working directory
    load_dotenv(override=True)

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    print(f"[*] Starting AGY2API on http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
