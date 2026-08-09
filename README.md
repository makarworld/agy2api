<div align="center">

# AGY2API

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.100%2B-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-supported-blue.svg)](https://www.docker.com/)

**A fully featured OpenAI-compatible API Wrapper for the Google Antigravity (AGY) CLI**

[Vietnamese (Tiếng Việt)](doc/README_vi.md)

</div>

## ✨ Core Features

- 🔄 **OpenAI Compatible** - Seamlessly integrates with AI clients like Cursor, Chatbox, Cline, and SillyTavern.
- 🖼️ **Multimodal Support** - Automatically extracts base64 files and images from the OpenAI payload, writes them to a managed temp directory, and passes them to the `agy` context.
- 🎨 **Image Generation** - Built-in support for `/v1/images/generations`.
- 🎙️ **Audio Generation** - Text-to-speech generation via `/v1/audio/speech`.
- 🛡️ **Secure Execution** - Implements an AGY PreToolUse hook (`safety_gate.py`) to intercept and block dangerous shell commands.
- 🚀 **Daemon Mode** - Run in the background using systemd or Docker.
- 📱 **UI Layer** - Integrated web UI for managing API keys and viewing logs.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ or Docker & Docker Compose
- Google Antigravity (`agy`) CLI installed and configured.

### Method 1: Docker Deployment (Recommended)

```bash
# Clone the repository
git clone https://github.com/truongqv12/agy2api.git
cd agy2api

# Start the service
docker-compose up -d

# View logs
docker-compose logs -f
```

### Method 2: Local Deployment

```bash
# Clone the repository
git clone https://github.com/truongqv12/agy2api.git
cd agy2api

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt

# Configure your API key
export AGY_API_KEY="your-secret-key"

# Start the service
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Systemd (User Service)
1. Copy `agy-wrapper.service` to `~/.config/systemd/user/`.
2. Edit paths inside the service file.
3. Run `systemctl --user daemon-reload`
4. Run `systemctl --user enable --now agy-wrapper`

## 🛡️ Safety Hooks

To enable the safety gate in your local `agy` environment, link or copy `hooks.json` to your `~/.gemini/config/hooks.json` or `.agents/hooks.json`.

## 🔌 API Endpoints
- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/images/generations`
- `POST /v1/audio/speech`
- `GET /v1/audio/voices`
- `GET /api/keys` / `POST /api/keys`
- `GET /api/logs`

For a complete guide, please refer to the [API Documentation](API_DOCS.md).

## ⚙️ Usage with Cursor

In **Cursor Settings > Models**:
1. Override OpenAI API Base URL with `http://localhost:8000/v1`
2. Enter your `AGY_API_KEY`.
3. Add custom model names (e.g., `Gemini 3.6 Flash (High)`).
