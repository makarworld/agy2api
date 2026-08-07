---
phase: 3
title: "OpenAI Endpoints Implementation"
status: pending
priority: P1
effort: "4h"
dependencies: ["2"]
---

# Phase 3: OpenAI Endpoints Implementation

## Overview
Implement the core OpenAI-compatible endpoints: `/v1/chat/completions` and `/v1/models`.

## Requirements
- Functional: `/v1/chat/completions` accepts OpenAI payload, translates to `agy` prompt, and returns OpenAI response format.
- Functional: `/v1/models` returns static or dynamically fetched models.

## Architecture
- `app/api/models.py`: Pydantic schemas mimicking OpenAI's `ChatCompletionRequest` and `ChatCompletionResponse`.
- `app/api/routes.py`: FastAPI routers mapping to the core logic.

## Related Code Files
- Create: `app/api/models.py`, `app/api/routes.py`
- Modify: `app/main.py` (include router)

## Implementation Steps
1. Define Pydantic models for OpenAI Chat payload (messages array, model string, etc.).
2. In `/v1/chat/completions`, concatenate the `messages` array into a single logical prompt string suitable for `agy` (e.g., formatting as "Role: message").
3. Call `run_agy_prompt` with the generated string.
4. Parse the output JSON from `agy` and wrap it in the `ChatCompletionResponse` structure.
5. Define `/v1/models` to return a list of valid models (e.g., "Gemini 3.1 Pro (High)", "Gemini 3.6 Flash (High)").

## Success Criteria
- [ ] Valid requests to `/v1/chat/completions` succeed and return the exact JSON structure expected by OpenAI clients.
- [ ] `/v1/models` returns the models list in OpenAI's data list format.

## Risk Assessment
- Output from `agy` might contain ANSI codes or extra text outside JSON. Mitigation: We must ensure `--output-format json` guarantees clean stdout, or parse it carefully (extracting JSON between { }).
