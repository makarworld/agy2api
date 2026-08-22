import json
import time
import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse

from app.api.anthropic_models import AnthropicMessagesRequest
from app.core.security import get_anthropic_api_key
from app.core.agy_runner import run_completion, stream_agy_completion
from app.core.file_handler import TempFileManager
from app.core.model_manager import get_available_models, MODEL_ALIASES
from app.core import stats_store
from app.core import pool_manager

logger = logging.getLogger(__name__)

router = APIRouter()


async def resolve_agy_model(requested: str) -> str:
    """Maps an Anthropic-style model name to whatever agy CLI actually exposes."""
    if requested in MODEL_ALIASES:
        return MODEL_ALIASES[requested]

    models = await get_available_models()
    ids = [m.id for m in models]

    if requested in ids:
        return requested

    lower = requested.lower()
    for m in ids:
        if m.lower() == lower:
            return m

    if "opus" in lower:
        for m in ids:
            if "opus" in m.lower():
                return m
        return "claude-opus-4-6-thinking"

    if "haiku" in lower:
        for m in ids:
            if "flash" in m.lower() and "low" in m.lower():
                return m
        return "gemini-3.5-flash-low"

    # sonnet or anything else -> default balanced model
    for m in ids:
        if "sonnet" in m.lower():
            return m
    return "claude-sonnet-4-6"


def _extract_system_text(system) -> Optional[str]:
    if not system:
        return None
    if isinstance(system, str):
        return system
    text_parts = [b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"]
    return " ".join(text_parts) if text_parts else None


def _build_messages(system, messages, file_mgr: TempFileManager):
    """Returns (normalized [{"role","content":str}], system_text, files_to_attach)."""
    files_to_attach = []
    normalized = []

    for msg in messages:
        role = msg.role
        content = msg.content

        if isinstance(content, str):
            normalized.append({"role": role, "content": content})
            continue

        text_parts = []
        for block in content:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "image":
                source = block.get("source", {})
                media_type = source.get("media_type", "image/png")
                data = source.get("data", "")
                ext = ".png"
                if "jpeg" in media_type or "jpg" in media_type:
                    ext = ".jpg"
                elif "gif" in media_type:
                    ext = ".gif"
                elif "webp" in media_type:
                    ext = ".webp"
                try:
                    fpath = file_mgr.add_base64_file(data, ext=ext)
                    files_to_attach.append(fpath)
                    text_parts.append(f"[Attached Image: {fpath}]")
                except Exception as e:
                    text_parts.append(f"[Failed to attach image: {e}]")
            elif btype == "document":
                source = block.get("source", {})
                media_type = source.get("media_type", "application/pdf")
                data = source.get("data", "")
                ext = ".pdf" if "pdf" in media_type else ".bin"
                try:
                    fpath = file_mgr.add_base64_file(data, ext=ext)
                    files_to_attach.append(fpath)
                    text_parts.append(f"[Attached Document: {fpath}]")
                except Exception as e:
                    text_parts.append(f"[Failed to attach document: {e}]")
            elif btype == "tool_result":
                tr_content = block.get("content", "")
                if isinstance(tr_content, list):
                    tr_text = " ".join(b.get("text", "") for b in tr_content if isinstance(b, dict))
                else:
                    tr_text = str(tr_content)
                text_parts.append(f"[Tool Result: {tr_text}]")
            elif btype == "tool_use":
                text_parts.append(f"[Tool Use: {block.get('name')} input={json.dumps(block.get('input', {}))}]")

        normalized.append({"role": role, "content": " ".join(text_parts)})

    return normalized, _extract_system_text(system), files_to_attach


def _extract_text(agy_response) -> str:
    if isinstance(agy_response, dict):
        return agy_response.get("text") or agy_response.get("content") or agy_response.get("response") or str(agy_response)
    return str(agy_response)


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _stream_response(messages: List[dict], system: Optional[str], agy_model: str, client_model: str, start_time: float):
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    fallback_prompt_tokens = max(1, sum(len(m["content"]) for m in messages) // 4)

    yield _sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": client_model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": fallback_prompt_tokens, "output_tokens": 0, "cache_read_input_tokens": 0},
        },
    })
    yield _sse("content_block_start", {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    })

    final_usage = {}
    try:
        async for piece in stream_agy_completion(messages=messages, system=system, model=agy_model):
            if "delta" in piece:
                yield _sse("content_block_delta", {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": piece["delta"]},
                })
            if "usage" in piece:
                final_usage = piece.get("usage", {})
    except Exception as e:
        await stats_store.record_request(
            endpoint="anthropic-chat", model=client_model, pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=0, completion_tokens=0, cache_tokens=0, success=False,
            latency_ms=int((time.time() - start_time) * 1000), error_type=type(e).__name__,
        )
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
        yield _sse("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": "error", "stop_sequence": None},
            "usage": {"output_tokens": 0},
        })
        yield _sse("message_stop", {"type": "message_stop"})
        return

    prompt_tokens = final_usage.get("input_tokens", fallback_prompt_tokens)
    completion_tokens = final_usage.get("output_tokens", 0) + final_usage.get("thinking_tokens", 0)
    cache_tokens = final_usage.get("cache_read_tokens", 0)

    await stats_store.record_request(
        endpoint="anthropic-chat", model=client_model, pool_account=pool_manager.get_active_account_id(),
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cache_tokens=cache_tokens,
        success=True, latency_ms=int((time.time() - start_time) * 1000), error_type=None,
    )

    yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield _sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": completion_tokens},
    })
    yield _sse("message_stop", {"type": "message_stop"})


@router.post("/messages", summary="Create a Message (Anthropic-compatible)")
async def create_message(
    req: AnthropicMessagesRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_anthropic_api_key),
):
    logger.info(f"[anthropic] Processing message request for model: {req.model}")
    start_time = time.time()
    file_mgr = TempFileManager()
    background_tasks.add_task(file_mgr.cleanup)

    messages, system, files = _build_messages(req.system, req.messages, file_mgr)
    agy_model = await resolve_agy_model(req.model)

    if req.stream:
        return StreamingResponse(
            _stream_response(messages, system, agy_model, req.model, start_time),
            media_type="text/event-stream",
        )

    try:
        agy_response = await run_completion(messages=messages, system=system, model=agy_model)
    except Exception as e:
        await stats_store.record_request(
            endpoint="anthropic-chat", model=req.model, pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=0, completion_tokens=0, cache_tokens=0, success=False,
            latency_ms=int((time.time() - start_time) * 1000), error_type=type(e).__name__,
        )
        raise

    assistant_text = _extract_text(agy_response)

    agy_usage = agy_response.get("usage") if isinstance(agy_response, dict) else None
    if isinstance(agy_usage, dict) and agy_usage:
        prompt_tokens = agy_usage.get("input_tokens", 0)
        completion_tokens = agy_usage.get("output_tokens", 0) + agy_usage.get("thinking_tokens", 0)
        cache_tokens = agy_usage.get("cache_read_tokens", 0)
    else:
        prompt_tokens = max(1, sum(len(m["content"]) for m in messages) // 4)
        completion_tokens = max(1, len(assistant_text) // 4)
        cache_tokens = 0

    await stats_store.record_request(
        endpoint="anthropic-chat", model=req.model, pool_account=pool_manager.get_active_account_id(),
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cache_tokens=cache_tokens,
        success=True, latency_ms=int((time.time() - start_time) * 1000), error_type=None,
    )

    return JSONResponse(content={
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": req.model,
        "content": [{"type": "text", "text": assistant_text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "cache_read_input_tokens": cache_tokens,
        },
    })
