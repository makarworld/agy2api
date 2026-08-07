---
title: "AGY2API UI Layer"
description: "A simple UI layer for agy2api to manage API keys, view logs, and test chat with goclaw's styling."
status: done
priority: P1
effort: "2d"
tags: [ui, react, fastapi]
created: 2026-08-07
---

# AGY2API UI Layer

## Overview

Build a simple Vite+React UI layer inside `agy2api/ui` and serve it via FastAPI. The UI will adopt the premium design language from `goclaw` but communicate exclusively via HTTP REST instead of WebSocket. It will provide API key configuration, log viewing, and a chat interface with image support.

## Goals

| # | Goal | Priority |
|---|------|----------|
| 1 | Setup React+Vite app in `ui/` directory and configure FastAPI to serve static files. | P1 |
| 2 | Create API Key configuration (LocalStorage) and Log Viewer (polling/SSE via new FastAPI endpoint). | P1 |
| 3 | Build Chat Interface supporting file/image upload (Base64) to `POST /v1/chat/completions`. | P1 |
| 4 | Adopt `goclaw` styling (Tailwind, Radix/shadcn). | P1 |

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Phase 1: Project Setup](./phase-01-start.md) | Pending |
| 2 | [Phase 2: API Keys & Log Viewer](./phase-02-keys-and-logs.md) | Pending |
| 3 | [Phase 3: Chat Interface](./phase-03-chat.md) | Pending |

## Success Criteria

- [ ] FastAPI serves a production build of the Vite app at `/`.
- [ ] UI can set API keys in LocalStorage and send them in `Authorization: Bearer <key>`.
- [ ] Logs can be viewed from the UI.
- [ ] Chat interface allows text and image prompting via REST.

<!-- slug: agy2api-ui-layer -->