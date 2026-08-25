import json
import time
import uuid
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, JSONResponse

from app.api.anthropic_models import AnthropicMessagesRequest
from app.core.security import get_anthropic_api_key
from app.core.agy_runner import run_completion, stream_agy_completion, with_heartbeat
from app.core.auto_classifier import is_auto_classifier_request, shortcut_enabled, shortcut_response
from app.core.file_handler import TempFileManager
from app.core.http_tools_bridge import stream_tool_call_key
from app.core.model_manager import resolve_backend_model, get_force_model
from app.core import stats_store
from app.core import pool_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_system_text(system) -> Optional[str]:
    if not system:
        return None
    if isinstance(system, str):
        return system
    text_parts = [b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"]
    return " ".join(text_parts) if text_parts else None


def _tool_result_text(content) -> str:
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content) if content is not None else ""


def _message_char_len(msg: dict) -> int:
    content = msg.get("content", "")
    n = len(content) if isinstance(content, str) else 0
    for tc in msg.get("tool_calls") or []:
        n += len(json.dumps(tc.get("input", {})))
    for tr in msg.get("tool_results") or []:
        n += len(_tool_result_text(tr.get("content")))
    return n


def _build_messages(system, messages, file_mgr: TempFileManager):
    """Returns (normalized messages, system_text, files_to_attach)."""
    files_to_attach = []
    normalized = []

    for msg in messages:
        role = msg.role
        content = msg.content

        if isinstance(content, str):
            normalized.append({"role": role, "content": content})
            continue

        text_parts: List[str] = []
        tool_calls: List[dict] = []
        tool_results: List[dict] = []
        images: List[dict] = []

        for block in content:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "image":
                source = block.get("source", {})
                media_type = source.get("media_type", "image/png")
                data = source.get("data", "")
                if data:
                    images.append({"mime_type": media_type, "data": data})
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
                    # For CLI transport fallback
                    # For HTTP transport, inlineData is used directly
                except Exception as e:
                    logger.warning(f"Failed to save temp file for image: {e}")
            elif btype == "document":
                source = block.get("source", {})
                media_type = source.get("media_type", "application/pdf")
                data = source.get("data", "")
                if data:
                    images.append({"mime_type": media_type, "data": data})
                ext = ".pdf" if "pdf" in media_type else ".bin"
                try:
                    fpath = file_mgr.add_base64_file(data, ext=ext)
                    files_to_attach.append(fpath)
                except Exception as e:
                    logger.warning(f"Failed to save temp file for document: {e}")
            elif btype == "tool_result":
                tool_results.append(
                    {
                        "tool_use_id": block.get("tool_use_id", ""),
                        "content": block.get("content", ""),
                        "is_error": block.get("is_error", False),
                        "name": block.get("name"),
                    }
                )
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "input": block.get("input", {}),
                    }
                )

        entry: dict = {"role": role}
        if text_parts:
            entry["content"] = " ".join(text_parts)
        elif tool_calls and role == "assistant":
            entry["content"] = ""
        elif tool_results and role == "user":
            entry["content"] = ""
        else:
            entry["content"] = ""
        if images:
            entry["images"] = images
        if tool_calls:
            entry["tool_calls"] = tool_calls
        if tool_results:
            entry["tool_results"] = tool_results
        normalized.append(entry)

    return normalized, _extract_system_text(system), files_to_attach


def _extract_text(agy_response) -> str:
    if isinstance(agy_response, dict):
        return (
            agy_response.get("text") or agy_response.get("content") or agy_response.get("response") or str(agy_response)
        )
    return str(agy_response)


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _tool_dedupe_key(tc: dict) -> str:
    tc_id = (tc.get("id") or "").strip()
    if tc_id:
        return f"id:{tc_id}"
    return stream_tool_call_key(tc)


async def _stream_classifier_shortcut(
    client_model: str,
    start_time: float,
    chat_id: str,
    chat_title: str,
    prompt_preview: str,
    *,
    prompt_tokens: int,
    response_text: str,
):
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    completion_tokens = max(1, len(response_text) // 4)

    yield _sse(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": client_model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": prompt_tokens, "output_tokens": 0, "cache_read_input_tokens": 0},
            },
        },
    )
    yield _sse(
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
    )
    yield _sse(
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": response_text},
        },
    )
    yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield _sse(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": completion_tokens},
        },
    )
    yield _sse("message_stop", {"type": "message_stop"})

    await stats_store.record_request(
        endpoint="anthropic-classifier-shortcut",
        model=client_model,
        pool_account=pool_manager.get_active_account_id(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_tokens=0,
        success=True,
        latency_ms=int((time.time() - start_time) * 1000),
        error_type=None,
        chat_id=chat_id,
        chat_title=chat_title,
        prompt_preview=prompt_preview,
        response_preview=response_text,
    )


async def _stream_response(
    messages: List[dict],
    system: Optional[str],
    agy_model: str,
    client_model: str,
    start_time: float,
    chat_id: str,
    chat_title: str,
    prompt_preview: str,
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[Any] = None,
):
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    fallback_prompt_tokens = max(1, sum(_message_char_len(m) for m in messages) // 4)

    yield _sse(
        "message_start",
        {
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
        },
    )

    final_usage: dict = {}
    assistant_chunks: List[str] = []
    tool_calls_collected: List[dict] = []
    emitted_tool_keys: set[str] = set()
    text_block_open = False
    block_index = 0
    stop_reason = "end_turn"
    error_message: Optional[str] = None

    try:
        async for piece in with_heartbeat(
            stream_agy_completion(
                messages=messages,
                system=system,
                model=agy_model,
                tools=tools,
                tool_choice=tool_choice,
            )
        ):
            if piece is None:
                yield ": ping\n\n"
                continue

            if "tool_calls" in piece and "usage" not in piece:
                for tc in piece["tool_calls"]:
                    tool_key = _tool_dedupe_key(tc)
                    if tool_key in emitted_tool_keys:
                        continue
                    emitted_tool_keys.add(tool_key)

                    if text_block_open:
                        yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
                        text_block_open = False

                    block_index += 1
                    tool_id = tc.get("id") or f"toolu_{uuid.uuid4().hex[:24]}"
                    tool_name = tc.get("name", "")
                    tool_input = tc.get("input", {})
                    tool_calls_collected.append(tc)

                    yield _sse(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": block_index,
                            "content_block": {
                                "type": "tool_use",
                                "id": tool_id,
                                "name": tool_name,
                                "input": {},
                            },
                        },
                    )
                    yield _sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block_index,
                            "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_input)},
                        },
                    )
                    yield _sse("content_block_stop", {"type": "content_block_stop", "index": block_index})

            if "delta" in piece:
                if not text_block_open:
                    yield _sse(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": 0,
                            "content_block": {"type": "text", "text": ""},
                        },
                    )
                    text_block_open = True
                assistant_chunks.append(piece["delta"])
                yield _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": piece["delta"]},
                    },
                )

            if "usage" in piece:
                final_usage = piece.get("usage", {})
                if piece.get("stop_reason"):
                    stop_reason = piece["stop_reason"]
                if piece.get("error"):
                    error_message = piece["error"]
                if piece.get("tool_calls"):
                    for tc in piece["tool_calls"]:
                        tool_key = _tool_dedupe_key(tc)
                        if tool_key in emitted_tool_keys:
                            continue
                        emitted_tool_keys.add(tool_key)
                        tool_calls_collected.append(tc)
    except Exception as e:
        logger.error(f"[anthropic] Stream exception ({type(e).__name__}): {e}")
        await stats_store.record_request(
            endpoint="anthropic-chat",
            model=client_model,
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=0,
            completion_tokens=0,
            cache_tokens=0,
            success=False,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=type(e).__name__,
            chat_id=chat_id,
            chat_title=chat_title,
            prompt_preview=prompt_preview,
            response_preview=f"Error: {str(e)}",
        )
        if text_block_open:
            yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})

        empty_on_error = os.environ.get("AGY_HTTP_EMPTY_AS_EMPTY_CONTENT", "true").lower() in ("true", "1", "yes")
        if empty_on_error and not assistant_chunks and not tool_calls_collected:
            logger.info(f"[anthropic] Returning empty content [] on stream {type(e).__name__} for client auto-retry")
            yield _sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 0},
                },
            )
        else:
            yield _sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "error", "stop_sequence": None},
                    "usage": {"output_tokens": 0},
                },
            )
        yield _sse("message_stop", {"type": "message_stop"})
        return

    assistant_text = "".join(assistant_chunks)
    if tool_calls_collected:
        stop_reason = "tool_use"

    if not error_message and not assistant_text and not tool_calls_collected:
        # Empty response from upstream model: emit no content blocks and end_turn with 0 tokens.
        # Claude Code treats empty content [] as invisible output and automatically retries.
        stop_reason = "end_turn"
    elif error_message:
        if not assistant_text:
            yield _sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            )
            assistant_chunks.append(error_message)
            yield _sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": error_message},
                },
            )
            text_block_open = True
            assistant_text = error_message
        stop_reason = "error"

    prompt_tokens = final_usage.get("input_tokens", fallback_prompt_tokens)
    completion_tokens = final_usage.get("output_tokens", 0) + final_usage.get("thinking_tokens", 0)
    if completion_tokens == 0 and assistant_text:
        completion_tokens = max(1, len(assistant_text) // 4)
    if completion_tokens == 0 and tool_calls_collected:
        completion_tokens = max(1, len(json.dumps(tool_calls_collected)) // 4)
    cache_tokens = final_usage.get("cache_read_tokens", 0)

    is_error = stop_reason == "error"
    preview = assistant_text[:1500] if assistant_text else json.dumps(tool_calls_collected)[:1500]
    await stats_store.record_request(
        endpoint="anthropic-chat",
        model=client_model,
        pool_account=pool_manager.get_active_account_id(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_tokens=cache_tokens,
        success=not is_error,
        latency_ms=int((time.time() - start_time) * 1000),
        error_type="EmptyModelResponse" if is_error else None,
        chat_id=chat_id,
        chat_title=chat_title,
        prompt_preview=prompt_preview,
        response_preview=preview,
    )

    if text_block_open:
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield _sse(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": completion_tokens},
        },
    )
    yield _sse("message_stop", {"type": "message_stop"})


@router.post("/messages", summary="Create a Message (Anthropic-compatible)")
async def create_message(
    req: AnthropicMessagesRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    api_key: str = Depends(get_anthropic_api_key),
):
    logger.info(f"[anthropic] Processing message request for model: {req.model}")
    start_time = time.time()
    file_mgr = TempFileManager()
    background_tasks.add_task(file_mgr.cleanup)

    messages, system, files = _build_messages(req.system, req.messages, file_mgr)
    agy_model = await resolve_backend_model(req.model)
    if get_force_model():
        logger.info(f"[anthropic] Force model: requested={req.model} backend={agy_model}")

    user_identifier = None
    if req.metadata and isinstance(req.metadata, dict):
        user_identifier = (
            req.metadata.get("user_id") or req.metadata.get("session_id") or req.metadata.get("conversation_id")
        )

    chat_id, chat_title, prompt_preview = stats_store.extract_chat_metadata(
        headers=dict(request.headers),
        messages=messages,
        user_identifier=user_identifier,
        system_text=system,
    )

    if shortcut_enabled() and is_auto_classifier_request(messages, system=system):
        response_text = shortcut_response()
        prompt_tokens = max(1, sum(_message_char_len(m) for m in messages) // 4)
        logger.info("[anthropic] auto-classifier shortcut -> %s", response_text)
        if req.stream:
            return StreamingResponse(
                _stream_classifier_shortcut(
                    req.model,
                    start_time,
                    chat_id,
                    chat_title,
                    prompt_preview,
                    prompt_tokens=prompt_tokens,
                    response_text=response_text,
                ),
                media_type="text/event-stream",
            )

        completion_tokens = max(1, len(response_text) // 4)
        await stats_store.record_request(
            endpoint="anthropic-classifier-shortcut",
            model=req.model,
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_tokens=0,
            success=True,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=None,
            chat_id=chat_id,
            chat_title=chat_title,
            prompt_preview=prompt_preview,
            response_preview=response_text,
        )
        return JSONResponse(
            content={
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "model": req.model,
                "content": [{"type": "text", "text": response_text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "cache_read_input_tokens": 0,
                },
            }
        )

    if req.stream:
        return StreamingResponse(
            _stream_response(
                messages,
                system,
                agy_model,
                req.model,
                start_time,
                chat_id,
                chat_title,
                prompt_preview,
                tools=req.tools,
                tool_choice=req.tool_choice,
            ),
            media_type="text/event-stream",
        )

    try:
        agy_response = await run_completion(
            messages=messages,
            system=system,
            model=agy_model,
            tools=req.tools,
            tool_choice=req.tool_choice,
        )
    except Exception as e:
        logger.error(f"[anthropic] Message request exception ({type(e).__name__}): {e}")
        await stats_store.record_request(
            endpoint="anthropic-chat",
            model=req.model,
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=0,
            completion_tokens=0,
            cache_tokens=0,
            success=False,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=type(e).__name__,
            chat_id=chat_id,
            chat_title=chat_title,
            prompt_preview=prompt_preview,
            response_preview=f"Error: {str(e)}",
        )
        empty_on_error = os.environ.get("AGY_HTTP_EMPTY_AS_EMPTY_CONTENT", "true").lower() in ("true", "1", "yes")
        if empty_on_error:
            logger.info(
                f"[anthropic] Returning empty content [] on non-stream {type(e).__name__} for client auto-retry"
            )
            return JSONResponse(
                content={
                    "id": f"msg_{uuid.uuid4().hex[:24]}",
                    "type": "message",
                    "role": "assistant",
                    "model": req.model,
                    "content": [],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_read_input_tokens": 0,
                    },
                }
            )
        raise

    assistant_text = _extract_text(agy_response)
    tool_calls = agy_response.get("tool_calls", []) if isinstance(agy_response, dict) else []
    stop_reason = agy_response.get("stop_reason", "end_turn") if isinstance(agy_response, dict) else "end_turn"

    content_blocks: List[dict] = []
    if assistant_text:
        content_blocks.append({"type": "text", "text": assistant_text})
    for tc in tool_calls:
        content_blocks.append(
            {
                "type": "tool_use",
                "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                "name": tc.get("name", ""),
                "input": tc.get("input", {}),
            }
        )
    # If both text and tool_calls are empty, keep content_blocks as [] so client retries

    agy_usage = agy_response.get("usage") if isinstance(agy_response, dict) else None
    if isinstance(agy_usage, dict) and agy_usage:
        prompt_tokens = agy_usage.get("input_tokens", 0)
        completion_tokens = agy_usage.get("output_tokens", 0) + agy_usage.get("thinking_tokens", 0)
        cache_tokens = agy_usage.get("cache_read_tokens", 0)
    else:
        prompt_tokens = max(1, sum(_message_char_len(m) for m in messages) // 4)
        completion_tokens = (
            max(1, len(assistant_text) // 4) if assistant_text else max(1, len(json.dumps(tool_calls)) // 4)
        )
        cache_tokens = 0

    preview = assistant_text[:1500] if assistant_text else json.dumps(tool_calls)[:1500]
    await stats_store.record_request(
        endpoint="anthropic-chat",
        model=req.model,
        pool_account=pool_manager.get_active_account_id(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_tokens=cache_tokens,
        success=True,
        latency_ms=int((time.time() - start_time) * 1000),
        error_type=None,
        chat_id=chat_id,
        chat_title=chat_title,
        prompt_preview=prompt_preview,
        response_preview=preview,
    )

    return JSONResponse(
        content={
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "model": req.model,
            "content": content_blocks,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "cache_read_input_tokens": cache_tokens,
            },
        }
    )


@router.post("/messages/count_tokens", summary="Count tokens (Anthropic-compatible stub)")
async def count_message_tokens(
    req: AnthropicMessagesRequest,
    api_key: str = Depends(get_anthropic_api_key),
):
    """Rough token estimate so Claude Code does not retry on 405."""
    file_mgr = TempFileManager()
    messages, system, _ = _build_messages(req.system, req.messages, file_mgr)
    file_mgr.cleanup()

    estimate = max(1, sum(_message_char_len(m) for m in messages) // 4)
    if system:
        estimate += max(1, len(system) // 4)
    if req.tools:
        estimate += max(1, len(json.dumps(req.tools)) // 4)

    return JSONResponse(content={"input_tokens": estimate})
