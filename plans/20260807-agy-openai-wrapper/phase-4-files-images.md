---
phase: 4
title: "File Handling & Image Generation"
status: pending
priority: P2
effort: "4h"
dependencies: ["2", "3"]
---

# Phase 4: File Handling & Image Generation

## Overview
Handle file uploads (or base64 encoded images in messages) and implement the `/v1/images/generations` endpoint.

## Requirements
- Functional: When `messages` array contains `image_url` or file attachments, the API must decode the data, save it to a temporary file, and pass the path to `agy`.
- Functional: Implement `/v1/images/generations` to accept a prompt, ask `agy` to generate the image (e.g. using `ak:ai-artist` or similar skill logic), and return the URL or base64.

## Architecture
- `app/core/file_handler.py`: Context managers and utilities for writing base64 data to `tempfile` and returning absolute paths.

## Related Code Files
- Create: `app/core/file_handler.py`
- Modify: `app/api/routes.py`, `app/core/agy_runner.py`

## Implementation Steps
1. In `file_handler.py`, create a class or function that takes Base64 content, writes it to a temporary file in a managed directory (e.g., `/tmp/agy_wrapper/`), and registers it for deletion after the request.
2. In `/v1/chat/completions`, detect image/file parts in the payload. Save them using the handler.
3. Pass the resulting temporary file paths to `agy_runner.py` via an argument (e.g., `["--add-dir", "/tmp/agy_wrapper/"]` or by formatting the path directly into the text prompt `[Attached File: /tmp/agy_wrapper/abc.png]`).
4. Implement `/v1/images/generations` endpoint. Map the prompt to `agy` and extract the resulting image URL/base64 from the output JSON.
5. Ensure cleanup of temp files occurs in a `finally` block or FastAPI BackgroundTask.

## Success Criteria
- [ ] Uploading a base64 image in OpenAI chat payload successfully triggers `agy` vision capabilities.
- [ ] Temporary files are definitively deleted after the API request finishes.

## Risk Assessment
- Disk leak due to failed temp file deletion. Mitigation: use `tempfile.TemporaryDirectory` with a context manager in the request lifecycle.
