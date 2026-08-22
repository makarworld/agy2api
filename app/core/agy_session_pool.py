import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional

from app.core import pool_manager

logger = logging.getLogger(__name__)

IDLE_TIMEOUT_SECONDS = int(os.environ.get("AGY_WARM_IDLE_TIMEOUT_SECONDS", "600"))
MAX_SESSIONS = int(os.environ.get("AGY_WARM_MAX_SESSIONS", "20"))
GC_INTERVAL_SECONDS = 60


@dataclass
class _WarmSession:
    process: asyncio.subprocess.Process
    account_id: Optional[str]
    model: Optional[str]
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used_ts: float = field(default_factory=time.time)
    current_key: Optional[str] = None


_SESSIONS: Dict[str, _WarmSession] = {}
_REGISTRY_LOCK = asyncio.Lock()
_gc_task: Optional[asyncio.Task] = None


def _canonical(messages: List[dict]) -> str:
    return json.dumps(messages, sort_keys=True, ensure_ascii=False, default=str)


def _session_key(model: Optional[str], messages_prefix: List[dict]) -> str:
    # Deliberately NOT keyed by account: a warm hit continues whichever account
    # that specific conversation already started on (session.account_id), so
    # continuity beats rotation-fairness once a conversation is underway.
    raw = f"{model}|{_canonical(messages_prefix)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _kill(process: asyncio.subprocess.Process) -> None:
    try:
        if process.stdin and not process.stdin.is_closing():
            process.stdin.close()
    except Exception:
        pass
    try:
        process.kill()
        await asyncio.wait_for(process.wait(), timeout=5)
    except Exception:
        pass


async def _evict_locked(key: str) -> None:
    session = _SESSIONS.pop(key, None)
    if session is not None:
        asyncio.create_task(_kill(session.process))


async def _register(key: str, session: _WarmSession) -> None:
    async with _REGISTRY_LOCK:
        if session.current_key and session.current_key != key:
            _SESSIONS.pop(session.current_key, None)
        existing = _SESSIONS.get(key)
        if existing is not None and existing is not session:
            asyncio.create_task(_kill(existing.process))
        _SESSIONS[key] = session
        session.current_key = key
        if len(_SESSIONS) > MAX_SESSIONS:
            oldest_key = min(_SESSIONS, key=lambda k: _SESSIONS[k].last_used_ts)
            if oldest_key != key:
                await _evict_locked(oldest_key)


async def _unregister_session_object(session: _WarmSession) -> None:
    async with _REGISTRY_LOCK:
        if session.current_key:
            _SESSIONS.pop(session.current_key, None)
            session.current_key = None


async def _gc_loop() -> None:
    while True:
        await asyncio.sleep(GC_INTERVAL_SECONDS)
        try:
            now = time.time()
            async with _REGISTRY_LOCK:
                stale = [k for k, v in _SESSIONS.items() if now - v.last_used_ts > IDLE_TIMEOUT_SECONDS]
                for k in stale:
                    await _evict_locked(k)
        except Exception as e:
            logger.warning(f"[warm-pool] GC error: {e}")


def ensure_gc_started() -> None:
    global _gc_task
    if _gc_task is None or _gc_task.done():
        _gc_task = asyncio.create_task(_gc_loop())


async def shutdown() -> None:
    """Best-effort cleanup on app exit."""
    global _gc_task
    if _gc_task is not None:
        _gc_task.cancel()
    async with _REGISTRY_LOCK:
        for session in list(_SESSIONS.values()):
            asyncio.create_task(_kill(session.process))
        _SESSIONS.clear()


def _spawn_cmd(model: Optional[str]) -> List[str]:
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
    return cmd


async def _spawn_session(account_id: Optional[str], model: Optional[str]) -> _WarmSession:
    if account_id:
        await pool_manager.activate_account(account_id)
    process = await asyncio.create_subprocess_exec(
        *_spawn_cmd(model),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return _WarmSession(process=process, account_id=account_id, model=model)


def _stdin_message(text: str) -> bytes:
    return (json.dumps({
        "event": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }) + "\n").encode("utf-8")


async def _drain_stderr_tail(process: asyncio.subprocess.Process, max_bytes: int = 4000) -> str:
    try:
        data = await asyncio.wait_for(process.stderr.read(max_bytes), timeout=1)
        return data.decode(errors="replace")
    except Exception:
        return ""


async def _stream_turn_on_process(session: _WarmSession, text: str) -> AsyncIterator[dict]:
    process = session.process
    process.stdin.write(_stdin_message(text))
    await process.stdin.drain()

    while True:
        raw = await process.stdout.readline()
        if not raw:
            stderr_tail = await _drain_stderr_tail(process)
            raise RuntimeError(f"agy process ended unexpectedly (exit={process.returncode}): {stderr_tail[:2000]}")

        line = raw.decode(errors="replace").strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        event = obj.get("event")
        if event == "step_update":
            su = obj.get("step_update", {})
            if su.get("step_type") == "agent_response" and su.get("text_delta"):
                yield {"delta": su["text_delta"]}
        elif event == "result":
            result = obj.get("result", {})
            if result.get("status") not in (None, "SUCCESS"):
                stderr_tail = await _drain_stderr_tail(process)
                raise RuntimeError(f"agy turn failed (status={result.get('status')}): {stderr_tail[:2000]}")
            usage = result.get("usage", {})
            yield {
                "usage": usage,
                "text": result.get("response", ""),
            }
            return


async def send_turn(
    model: Optional[str],
    messages: List[dict],
    cold_prompt: str,
    pick_account,
) -> AsyncIterator[dict]:
    """messages: normalized [{"role","content":str}] full conversation including the new last message.
    cold_prompt: the fully-flattened prompt text to send if no warm session matches (same shape agy_runner
    uses for CLI mode) -- used only on a cache miss, so a fresh session gets the whole conversation in one turn.
    pick_account: async callable() -> Optional[str], invoked only on a cache miss (pool-mode account
    rotation); return None when the pool is disabled.
    """
    ensure_gc_started()

    prefix = messages[:-1]
    key = _session_key(model, prefix)

    async with _REGISTRY_LOCK:
        session = _SESSIONS.get(key)

    is_warm_hit = session is not None
    turn_text = messages[-1].get("content", "") if is_warm_hit else cold_prompt

    if not is_warm_hit:
        account_id = await pick_account() if pick_account else None
        session = await _spawn_session(account_id, model)

    assistant_text_parts: List[str] = []
    try:
        async with session.lock:
            async for chunk in _stream_turn_on_process(session, turn_text):
                if "delta" in chunk:
                    assistant_text_parts.append(chunk["delta"])
                yield chunk
    except Exception as e:
        await _unregister_session_object(session)
        asyncio.create_task(_kill(session.process))
        if session.account_id:
            combined = str(e).lower()
            if any(sig in combined for sig in pool_manager.RATE_LIMIT_SIGNALS):
                cooldown = int(os.environ.get("AGY_POOL_COOLDOWN_SECONDS", "3600"))
                await pool_manager.mark_rate_limited(session.account_id, cooldown)
            else:
                await pool_manager.mark_failure(session.account_id)
        raise

    session.last_used_ts = time.time()
    if session.account_id:
        await pool_manager.mark_success(session.account_id)
    assistant_text = "".join(assistant_text_parts)
    new_key = _session_key(
        model,
        messages + [{"role": "assistant", "content": assistant_text}],
    )
    await _register(new_key, session)
