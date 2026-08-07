---
title: "Phase 2: API Keys & Log Viewer"
status: todo
---

# Phase 2: API Keys & Log Viewer

## Overview

Build the UI components for managing API keys and viewing logs, adopting goclaw's visual language. API keys will be stored locally in the browser. Logs will be fetched from a new endpoint in `agy2api`.

## Requirements

- [x] Create a Settings or API Keys page.
- [x] Save the API key to `localStorage` and expose it via a React Context/Hook.
- [x] Implement `GET /v1/logs` in `agy2api/app/main.py` to read `agy-wrapper.service` logs or a local log file.
- [x] Create a Log Viewer page in the UI to fetch and display logs from `GET /v1/logs`.

## Implementation Steps

1. Create a `useApiKey` hook in `ui/src/hooks/use-api-key.ts` using `localStorage`.
2. Build an `ApiKeysPage` component matching `goclaw`'s `api-keys-page.tsx` style (cards, input fields).
3. Update `agy2api/app/main.py` to add `@app.get("/v1/logs")`. The endpoint reads the last 100 lines of the application log file or runs `journalctl -u agy-wrapper.service -n 100`.
4. Build a `LogsPage` component matching `goclaw`'s `logs-page.tsx` style (dark terminal window, monospace text).
5. Set up React Router for navigation between these pages.

## Todo

- [x] API Key hook and UI.
- [x] FastAPI `/v1/logs` endpoint.
- [x] Logs Viewer UI.

## Success Criteria

- API Key is saved locally and can be retrieved.
- Logs page correctly displays backend logs fetched via HTTP.
