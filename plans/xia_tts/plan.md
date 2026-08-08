# Implementation Plan: CapCut TTS & STT API -> OpenAI Wrapper

## 1. Overview
Implement OpenAI-compatible TTS (Text-to-Speech) and STT (Speech-to-Text) API wrappers using CapCut's backend, converted to an async workflow to fit seamlessly into the existing FastAPI application.

## 2. Requirements & Dependencies
- Use `httpx` (async) instead of `requests` (sync) to avoid blocking the event loop.
- Extract `capcut_tts_api/signer.py` and `capcut_tts_api/uploader.py` logic and rewrite them for `httpx`.
- Add `httpx` and `python-multipart` (for file uploads) to `requirements.txt`.

## 3. Implementation Steps

### Step 1: Install Dependencies (COMPLETED)
- Run `pip install httpx python-multipart requests` inside `.venv`
- Add `httpx`, `python-multipart`, and `requests` to `requirements.txt`.

### Step 2: Extract Signer & Build Models (COMPLETED)
- Create `app/core/capcut_api.py`.
- Port cryptographic signing logic.
- Add a cached `DeviceConfig` generator.

### Step 3: Implement Async Client (`AsyncCapCutClient`) (COMPLETED)
- Implemented `AsyncCapCutWrapper` in `app/core/capcut_api.py`.
- Async TTS and STT polling loops using `asyncio.to_thread`.

### Step 4: Add Audio Streaming Support (COMPLETED)
- Added `io.BytesIO` StreamingResponse for TTS audio bytes.
- Integrated `SubtitleResult` conversion into SRT, VTT, Text, and JSON.

### Step 5: Update FastAPI Routes (COMPLETED)
- In `app/api/models.py`, defined a `SpeechRequest` model compliant with the OpenAI schema.
- In `app/api/routes.py`, added `POST /v1/audio/speech` endpoint.
- In `app/api/routes.py`, added `POST /v1/audio/transcriptions` endpoint. Accepts `UploadFile` (multipart/form-data), saves it temporarily, calls `AsyncCapCutClient` for STT, and returns the transcription in the requested `response_format` (default JSON).

## 4. Rollback Strategy
If issues arise:
- The endpoints are purely additive. They won't break the existing routes.
- Remove `POST /v1/audio/speech` and `POST /v1/audio/transcriptions` and `app/core/capcut_api.py` to cleanly revert.
