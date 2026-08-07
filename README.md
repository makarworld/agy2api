# AGY OpenAI API Wrapper

This is a FastAPI-based REST API that wraps the Google Antigravity CLI (`agy`) into a 100% OpenAI-compatible endpoint structure. 

## Features
- **OpenAI Compatible**: Seamlessly integrates with tools like Cursor, Chatbox, or SillyTavern.
- **Background Execution**: Can be run as a daemon using systemd or Docker.
- **Secure**: Implements an AGY PreToolUse hook (`safety_gate.py`) to intercept and block dangerous shell commands.
- **Vision/Files**: Automatically extracts base64 files from OpenAI payload, writes them to a managed temp directory, and passes them to `agy`'s context.

## Quickstart

### Local (Uvicorn)
```bash
pip install -r requirements.txt
export AGY_API_KEY="your-secret-key"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker
```bash
docker-compose up -d
```

### Systemd (User Service)
1. Copy `agy-wrapper.service` to `~/.config/systemd/user/`.
2. Edit paths inside the service file.
3. Run `systemctl --user daemon-reload`
4. Run `systemctl --user enable --now agy-wrapper`

## Safety Hooks
To enable the safety gate in your local `agy` environment, link or copy `hooks.json` to your `~/.gemini/config/hooks.json` or `.agents/hooks.json`.

## Endpoints
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/images/generations`

## Usage with Cursor
In Cursor Settings > Models:
1. Override OpenAI API Base URL with `http://localhost:8000/v1`
2. Enter your `AGY_API_KEY`.
3. Add custom model names (e.g., `Gemini 3.6 Flash (High)`).
