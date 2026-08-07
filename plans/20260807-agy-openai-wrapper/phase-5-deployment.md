---
phase: 5
title: "Background Deployment Configuration"
status: pending
priority: P2
effort: "2h"
dependencies: ["1", "2", "3"]
---

# Phase 5: Background Deployment Configuration

## Overview
Provide Dockerization and Systemd configurations so the service can run in the background (daemonized).

## Requirements
- Functional: The user can start the wrapper as a background service without leaving a terminal open.

## Architecture
- `Dockerfile` & `docker-compose.yml`
- `agy-wrapper.service` (Systemd template)

## Related Code Files
- Create: `Dockerfile`, `docker-compose.yml`, `agy-wrapper.service`

## Implementation Steps
1. Write `Dockerfile` that uses Python 3.10+, installs requirements, and runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
   - *Note:* If running in Docker, `agy` must be installed inside the container or mounted as a volume. Given `agy` is a CLI, Systemd might be easier for local usage, so we'll provide both.
2. Write a `docker-compose.yml` for easy multi-container orchestration.
3. Write `agy-wrapper.service` as a template for `systemd` user service:
   ```ini
   [Unit]
   Description=AGY OpenAI API Wrapper
   [Service]
   ExecStart=/usr/bin/env uvicorn app.main:app --host 0.0.0.0 --port 8000
   Restart=always
   ...
   ```
4. Write instructions in `README.md` on how to enable the systemd service or use docker-compose.

## Success Criteria
- [ ] Service can be started via `systemctl --user start agy-wrapper` and stays alive.

## Risk Assessment
- `agy` CLI context/permissions issues when running under a different background user. Mitigation: run as a user systemd service (`systemctl --user`) so it inherits the user's `~/.gemini/` configuration.
