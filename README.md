<div align="center">

# AGY2API

**A fully featured OpenAI-compatible API Wrapper for the Google Antigravity (AGY) CLI**

English | [Tiếng Việt (Vietnamese)](doc/README_vi.md)

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Google Antigravity](https://img.shields.io/badge/Google_Antigravity_CLI-4285F4?logo=google&logoColor=white)](https://antigravity.google/product/antigravity-cli)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

> [!TIP]
> AGY2API acts as a seamless bridge between modern AI clients (Cursor, Cline, Chatbox) and your local Google Antigravity instance.

> [!IMPORTANT]
> **You MUST install and configure the [Google Antigravity (`agy`) CLI](https://antigravity.google/product/antigravity-cli) before running this API.**

> [!CAUTION]
> **SECURITY WARNING:** Do NOT expose this API to the public internet. While `hooks.json` provides a basic safety gate, this project essentially acts as a wrapper around a powerful command-line interface. It cannot guarantee 100% protection against sophisticated command injection attacks that might compromise your server.

## Overview

AGY2API is a Python-based Gateway built with FastAPI. It translates OpenAI-compatible REST API requests into Google Antigravity (`agy`) commands, allowing you to use AGY's powerful agentic capabilities in any tool that supports OpenAI endpoints.

### Architecture

```mermaid
flowchart LR
    classDef client fill:#e1f5fe,stroke:#01579b
    classDef core fill:#fff3e0,stroke:#e65100
    classDef cli fill:#e8f5e9,stroke:#1b5e20

    subgraph Clients["Access Domain"]
        direction LR
        IDE["IDEs<br/>Cursor · Cline"]
        WebUI["Web Clients<br/>Chatbox · SillyTavern"]
    end

    subgraph Gateway["AGY2API Gateway"]
        direction LR
        API["FastAPI Routes<br/>/v1/chat/completions"]
        Security["Safety Gate<br/>Command interception"]
        Files["File Handler<br/>Base64 Extraction"]
        
        API --> Security
        API --> Files
    end

    AGY["Google Antigravity CLI"]

    Clients --> API
    Security --> AGY
    Files --> AGY

    class IDE,WebUI client
    class API,Security,Files core
    class AGY cli
```

### Core capabilities

| Area | Capabilities |
| :-- | :-- |
| **APIs** | Fully compatible with OpenAI Chat Completions, Image Generation, and Audio Speech |
| **Clients** | Works flawlessly with Cursor, Cline, Chatbox, and SillyTavern |
| **Multimodal & Vision** | Read and analyze images, perform OCR on documents/PDFs, and support image-to-image generation |
| **File Handling** | Automatically extracts base64 files from requests, writes them to a managed temp directory, and passes them to AGY |
| **Security** | Implements an AGY PreToolUse hook (`safety_gate.py`) to intercept and block dangerous shell commands |
| **Audio** | Text-to-speech generation via `/v1/audio/speech` (Powered by [capcut-tts-api](https://github.com/K07VN/capcut-tts-api)) |
| **Operations** | Integrated web UI for managing API keys and viewing logs, Daemon Mode (Docker & Systemd) |

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ or Docker & Docker Compose

### Method 1: Docker Deployment (Recommended)

```bash
# Clone the repository
git clone https://github.com/truongqv12/agy2api.git
cd agy2api

# Copy example environment file (and then edit it with your secret key)
cp .env.example .env

# Start the service (use 'docker-compose' for older Docker versions)
docker compose up -d

# View logs
docker compose logs -f
```

### Method 2: Local Deployment

```bash
# Clone the repository
git clone https://github.com/truongqv12/agy2api.git
cd agy2api

# Create and activate virtual environment (On Mac/Linux use python3)
python3 -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt

# Copy and configure your API key
cp .env.example .env
export AGY_API_KEY="your-secret-key"

# Start the service
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Method 3: Systemd Service (Linux only)

For a robust background service on Linux, you can use `systemd`. We have provided an `agy-wrapper.service` file for this purpose.

1. Open `agy-wrapper.service` and update the `WorkingDirectory`, `ExecStart`, and `EnvironmentFile` paths if your project is not located at `/home/truong/agy2api`.
2. Copy the service file to your systemd user directory:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp agy-wrapper.service ~/.config/systemd/user/
   ```
3. Reload systemd and enable the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now agy-wrapper
   ```
4. View logs:
   ```bash
   journalctl --user -u agy-wrapper -f
   ```

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

## 🎨 Developing the UI (Optional)

<p align="center">
  <img alt="AGY2API Dashboard" src="doc/screenshot.png" width="800" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);" />
</p>

If you chose **Method 2 (Local Deployment)** and want to access the Web UI, you must build it manually since the compiled `dist` folder is not included in the repository.

```bash
cd ui
npm install
npm run build
```
Once built, restart your Python server and the UI will be available at `http://localhost:8000/`. Alternatively, you can run `npm run dev` to start a Vite development server with hot-reloading.

