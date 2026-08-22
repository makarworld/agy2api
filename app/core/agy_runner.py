import asyncio
import json
import logging
import os
from typing import AsyncIterator, List, Optional, Union, Any

from app.core import pool_manager
from app.core import stats_store
from app.core import agy_session_pool
from app.core import agy_http_client

logger = logging.getLogger(__name__)


def transport() -> str:
    return os.environ.get("AGY_TRANSPORT", "cli").strip().lower()


def flatten_messages(system: Optional[str], messages: List[dict]) -> str:
    """messages: normalized role/content or structured tool fields."""
    lines = []
    if system:
        lines.append(f"System: {system}")
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, str) and content:
            lines.append(f"{role.capitalize()}: {content}")
        for tc in m.get("tool_calls") or []:
            lines.append(f"{role.capitalize()} [tool_use {tc.get('name')}: {json.dumps(tc.get('input', {}))}]")
        for tr in m.get("tool_results") or []:
            lines.append(f"{role.capitalize()} [tool_result {tr.get('tool_use_id')}: {tr.get('content')}]")
    lines.append("Assistant: ")
    return "\n".join(lines)


async def fake_chunk_text(text: str, chunk_size: int = 24, delay: float = 0.005) -> AsyncIterator[str]:
    """Splits an already-complete response into small pieces for a simulated stream.
    Used by CLI transport, which has no real incremental output to relay."""
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]
        await asyncio.sleep(delay)


async def with_heartbeat(
    async_iter: AsyncIterator[dict],
    interval: float = 10.0,
) -> AsyncIterator[Union[dict, None]]:
    """Wrap an async generator; yields None when a SSE keepalive ping should be sent."""
    pending: Optional[asyncio.Task] = None
    iterator = async_iter.__aiter__()

    async def _next_chunk():
        return await iterator.__anext__()

    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(_next_chunk())
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield None
                continue
            try:
                yield pending.result()
            except StopAsyncIteration:
                break
            finally:
                pending = None
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration):
                pass


async def _stream_warm(
    messages: List[dict], system: Optional[str], model: Optional[str]
) -> AsyncIterator[dict]:
    async for chunk in agy_session_pool.send_turn(
        model, messages, flatten_messages(system, messages), _pick_pool_account
    ):
        yield chunk


async def _stream_cli(
    messages: List[dict], system: Optional[str], model: Optional[str]
) -> AsyncIterator[dict]:
    result = await run_agy_prompt(prompt=flatten_messages(system, messages), model=model)
    text = ""
    if isinstance(result, dict):
        text = result.get("text") or result.get("content") or result.get("response") or ""
    async for piece in fake_chunk_text(text):
        yield {"delta": piece}
    yield {"usage": result.get("usage", {}) if isinstance(result, dict) else {}, "text": text}


async def _stream_http(
    messages: List[dict],
    system: Optional[str],
    model: Optional[str],
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[Any] = None,
) -> AsyncIterator[dict]:
    async for chunk in agy_http_client.stream_completion(
        messages=messages,
        system=system,
        model=model,
        tools=tools,
        tool_choice=tool_choice,
    ):
        yield chunk


async def _run_http_completion(
    messages: List[dict],
    system: Optional[str],
    model: Optional[str],
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[Any] = None,
) -> dict:
    final: dict = {"text": "", "usage": {}, "tool_calls": [], "stop_reason": "end_turn"}
    async for chunk in agy_http_client.stream_completion(
        messages=messages,
        system=system,
        model=model,
        tools=tools,
        tool_choice=tool_choice,
    ):
        if "delta" in chunk:
            final["text"] += chunk["delta"]
        if "tool_calls" in chunk:
            final["tool_calls"] = chunk["tool_calls"]
        if "usage" in chunk:
            final["usage"] = chunk.get("usage", {})
            if chunk.get("text"):
                final["text"] = chunk["text"]
            if chunk.get("tool_calls"):
                final["tool_calls"] = chunk["tool_calls"]
            if chunk.get("stop_reason"):
                final["stop_reason"] = chunk["stop_reason"]
    return final


async def _pick_pool_account() -> Optional[str]:
    if not pool_manager.pool_enabled():
        return None
    account = await pool_manager.select_next_healthy_account()
    if account is None:
        raise RuntimeError("All pool accounts are rate-limited or unhealthy")
    return account["id"]


_downtime_lock = asyncio.Lock()
_consecutive_failures = 0
_is_down = False


async def _note_success():
    global _consecutive_failures, _is_down
    async with _downtime_lock:
        _consecutive_failures = 0
        if _is_down:
            _is_down = False
            await stats_store.record_availability_event("up")


async def _note_failure(error_msg: str):
    global _consecutive_failures, _is_down
    threshold = int(os.environ.get("AGY_STATS_DOWN_THRESHOLD", "3"))
    async with _downtime_lock:
        _consecutive_failures += 1
        if not _is_down and _consecutive_failures >= threshold:
            _is_down = True
            await stats_store.record_availability_event("down", reason=error_msg[:500])


def _parse_stream_json_result(output_str: str) -> dict:
    """agy's stream-json output is NDJSON (one event per line); the final
    `result` event carries the same {response, usage, ...} shape the old flat
    --output-format json used to return directly."""
    result = None
    for line in output_str.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("event") == "result":
            result = obj.get("result", {})
    if result is not None:
        return result
    logger.error(f"No 'result' event found in AGY stream-json output: {output_str}")
    return {"text": output_str}


async def run_agy_prompt(prompt: str, model: str = None, files: list[str] = None):
    """
    Safely executes the `agy` CLI. Subprocess execution goes through
    pool_manager.execute_agy(), which is a transparent passthrough when the
    account pool is disabled (AGY_POOL_ENABLED=false, the default).

    The prompt is sent via stdin using agy's stream-json input format rather
    than as a `--print <prompt>` command-line argument. Windows has a hard
    command-line length limit (~32K chars) that large prompts -- e.g. a full
    Cursor Agent system prompt plus context -- blow straight past, crashing
    subprocess creation with WinError 206 ("filename or extension too long").
    Stdin has no such limit.
    """
    cmd = [
        "agy",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--print=",
        "--dangerously-skip-permissions",
        "--print-timeout", "10m",
    ]

    if model:
        cmd.extend(["--model", model])

    if files:
        for f in files:
            # File paths are already injected into the prompt text by the caller.
            pass

    stdin_message = json.dumps({
        "event": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
    }) + "\n"

    safe_cmd_log = ' '.join(cmd)
    logger.info(f"Executing AGY command: {safe_cmd_log}")

    returncode, stdout, stderr = await pool_manager.execute_agy(
        cmd, timeout=None, input_data=stdin_message.encode("utf-8")
    )

    if returncode != 0:
        error_msg = stderr.decode(errors="replace").strip()
        if not error_msg:
            error_msg = stdout.decode(errors="replace").strip()
        logger.error(f"AGY Error: {error_msg}")
        await _note_failure(error_msg)
        raise RuntimeError(f"AGY CLI execution failed: {error_msg}")

    await _note_success()

    output_str = stdout.decode(errors="replace").strip()
    return _parse_stream_json_result(output_str)


async def run_completion(
    messages: List[dict],
    system: Optional[str] = None,
    model: str = None,
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[Any] = None,
) -> dict:
    """Structured-message entrypoint shared by /v1/chat/completions and /anthropic/v1/messages
    for non-streaming requests."""
    mode = transport()
    if mode == "http":
        return await _run_http_completion(messages, system, model, tools=tools, tool_choice=tool_choice)

    if mode == "warm":
        cold_prompt = flatten_messages(system, messages)
        final = {"text": "", "usage": {}}
        async for chunk in agy_session_pool.send_turn(model, messages, cold_prompt, _pick_pool_account):
            if "usage" in chunk:
                final = {"text": chunk.get("text", ""), "usage": chunk.get("usage", {})}
        return final

    return await run_agy_prompt(prompt=flatten_messages(system, messages), model=model)


async def stream_agy_completion(
    messages: List[dict],
    system: Optional[str] = None,
    model: str = None,
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[Any] = None,
) -> AsyncIterator[dict]:
    """Real streaming for warm/http transport; simulated streaming for cli."""
    mode = transport()
    if mode == "http":
        async for chunk in _stream_http(messages, system, model, tools=tools, tool_choice=tool_choice):
            yield chunk
        return

    if mode == "warm":
        async for chunk in _stream_warm(messages, system, model):
            yield chunk
        return

    async for chunk in _stream_cli(messages, system, model):
        yield chunk
