---
phase: 2
title: "Security & CLI Execution Core"
status: pending
priority: P1
effort: "4h"
dependencies: ["1"]
---

# Phase 2: Security & CLI Execution Core

## Overview
Implement API Key authentication, the core logic to safely execute `agy` commands via Python subprocesses, and an AGY Lifecycle Hook to block dangerous shell commands.

## Requirements
- Functional: Ensure API requests require a valid Bearer token.
- Functional: Safely call `agy` with arguments without risking shell injection.
- Functional: Implement a `PreToolUse` hook in AGY that acts as a Safety Gate. It must intercept `run_command` tool calls, check against a denylist (e.g. `rm -rf`, `mkfs`), and return `{"decision": "deny"}` if matched.
- Non-functional: Must use async `asyncio.create_subprocess_exec` to not block the event loop.

## Architecture
- `app/core/security.py`: API key validation logic using FastAPI `Depends`.
- `app/core/agy_runner.py`: Wrapper around `asyncio.create_subprocess_exec`.
- `hooks.json` & `scripts/safety_gate.py`: AGY Lifecycle Hook configurations to intercept tool calls.

## Related Code Files
- Create: `app/core/security.py`, `app/core/agy_runner.py`
- Create: `hooks.json`, `scripts/safety_gate.py`

## Implementation Steps
1. Create `security.py` with `API_KEY` loaded from environment variables and a FastAPI dependency for checking the header `Authorization: Bearer <token>`.
2. Create `agy_runner.py` with a function `async def run_agy_prompt(...)`. The runner must build the command list securely.
3. Write `scripts/safety_gate.py` which reads stdin (a JSON payload from AGY), extracts `toolCall.args.CommandLine`, and checks a blacklist array. It prints `{"decision": "deny", "reason": "Blocked by API wrapper safety gate"}` to stdout if a threat is found, otherwise `{"decision": "allow"}`.
4. Create `hooks.json` mapping `safety-gate` to `PreToolUse` matching `"run_command"` that executes `scripts/safety_gate.py`.

## Success Criteria
- [ ] Unauthorized requests return 401.
- [ ] Safe execution of a hardcoded prompt via `agy_runner.py` returns JSON string.
- [ ] Passing a prompt asking to run a dangerous command gets blocked by the Hook script.

## Risk Assessment
- Command injection from prompt. Mitigation: Subprocess list wrapping.
- Evasion of the safety gate. Mitigation: Strict regex matching or simple word-boundary matching on `rm`, `chmod -R`, etc., inside `safety_gate.py`.
