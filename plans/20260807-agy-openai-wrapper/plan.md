---
title: "AGY OpenAI API Wrapper"
status: active
createdAt: "2026-08-07"
---

# AGY OpenAI API Wrapper Plan

## Overview
A background service (Python/FastAPI) that wraps the `agy` CLI to provide a 100% OpenAI-compatible REST API. It allows any OpenAI-compatible client (Cursor, Chatbox, etc.) to use `agy` as a backend. Includes API key authentication, proper temporary file handling for attachments, and background execution via Docker.

## Implementation Phases

1. [x] [Phase 1: Project Scaffolding & Setup](phase-1-setup.md)
2. [x] [Phase 2: Security & CLI Execution Core](phase-2-core.md)
3. [x] [Phase 3: OpenAI Endpoints Implementation](phase-3-endpoints.md)
4. [x] [Phase 4: File Handling & Image Generation](phase-4-files.md)
5. [x] [Phase 5: Background Deployment Configuration](phase-5-deployment.md)

## Red Team Notes
- Shell injection is the biggest risk. We must use `subprocess.run` with a list of arguments, NEVER `shell=True`.
- Uncleaned temporary files could exhaust disk space. We must use `tempfile.NamedTemporaryFile` or context managers to ensure cleanup even on exception.
- Long-running `agy` commands will block the API if we don't use async subprocess calls (e.g. `asyncio.create_subprocess_exec`).

## Validation
- Does `agy` output clean JSON? Yes, with `--output-format json --dangerously-skip-permissions`.
- Is the OpenAI schema complex? Yes, but using standard Pydantic models (or `fastapi-openai-compat`) simplifies it.
