import io
import json
import logging
import os
import subprocess
import time
import uuid
from typing import Any, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.api.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    ModelList,
    SpeechRequest,
    Usage,
)
from app.core import pool_manager, stats_store
from app.core import agy_http_client
from app.core.agy_runner import (
    run_completion,
    stream_agy_completion,
    with_heartbeat,
)
from app.core.capcut_api import AsyncCapCutWrapper
from app.core.file_handler import TempFileManager
from app.core.key_manager import record_key_output_tokens
from app.core.model_manager import (
    get_available_models,
    get_force_model,
    resolve_backend_model,
    resolve_http_model,
)
from app.core.response_cache import get_cached_response, put_cached_response
from app.core.request_tracer import get_current_trace, start_trace
from app.api.audio_routes import router as audio_router
from app.api.image_routes import (
    ImageGenerationRequest,  # noqa: F401
    ImageGenerationResponse,  # noqa: F401
    ImageObject,  # noqa: F401
    SimpleImageRequest,  # noqa: F401
    router as image_router,
)
from app.api.system_routes import router as system_router
from app.core.security import get_api_key, get_optional_api_key

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(audio_router)
router.include_router(image_router)
router.include_router(system_router)


@router.get(
    "/models",
    response_model=ModelList,
    summary="List Models",
    description="Returns a list of available AI models.",
)
async def list_models(api_key: str = Depends(get_api_key)):
    models = await get_available_models()
    return ModelList(data=models)


def _extract_message_content_and_images(
    msg, file_mgr: TempFileManager, files_to_attach: list
) -> tuple[str, list[dict]]:
    if isinstance(msg.content, str):
        return msg.content, []
    text_parts = []
    images = []
    for p in msg.content:
        if p.get("type") == "text":
            text_parts.append(p.get("text", ""))
        elif p.get("type") == "image_url":
            url = p.get("image_url", {}).get("url", "")
            if url.startswith("data:"):
                import re

                ext = ".png"
                mime_type = "image/png"
                match = re.match(r"^data:([^/]+)/([^;,]+)(?:;base64)?,(.*)$", url)
                if match:
                    top_type = match.group(1).lower()
                    mime_sub = match.group(2).lower()
                    mime_type = f"{top_type}/{mime_sub}"
                    raw_data = match.group(3)
                    if raw_data:
                        images.append({"mime_type": mime_type, "data": raw_data})
                    if mime_sub in ["jpeg", "jpg"]:
                        ext = ".jpg"
                    elif mime_sub == "pdf":
                        ext = ".pdf"
                    elif mime_sub == "msword":
                        ext = ".doc"
                    elif "wordprocessingml" in mime_sub:
                        ext = ".docx"
                    elif mime_sub == "plain":
                        ext = ".txt"
                    elif mime_sub == "csv":
                        ext = ".csv"
                    elif mime_sub in ["png", "gif", "webp"]:
                        ext = f".{mime_sub}"
                    else:
                        ext = f".{mime_sub}"
                try:
                    fpath = file_mgr.add_base64_file(url, ext=ext)
                    files_to_attach.append(fpath)
                except Exception as e:
                    logger.warning(f"Failed to attach image: {e}")
            else:
                text_parts.append(f"[Image URL: {url}]")
    return " ".join(text_parts), images


def _usage_from_agy(agy_usage: dict | None, fallback_prompt_len: int, fallback_completion_len: int) -> Usage:
    # agy's own JSON payload carries real token usage (confirmed live: input_tokens,
    # output_tokens, thinking_tokens, cache_read_tokens, total_tokens). Fall back to a
    # character-count heuristic only if that field is ever missing.
    if isinstance(agy_usage, dict) and agy_usage:
        prompt_tokens = agy_usage.get("input_tokens", 0)
        completion_tokens = agy_usage.get("output_tokens", 0) + agy_usage.get("thinking_tokens", 0)
        cache_tokens = agy_usage.get("cache_read_tokens", 0)
        total_tokens = agy_usage.get("total_tokens", prompt_tokens + completion_tokens)
    else:
        prompt_tokens = max(1, fallback_prompt_len // 4)
        completion_tokens = max(1, fallback_completion_len // 4)
        cache_tokens = 0
        total_tokens = prompt_tokens + completion_tokens
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cache_tokens=cache_tokens,
    )


def _tool_dedupe_key(tc: dict) -> str:
    name = (tc.get("name") or "").strip()
    tc_id = (tc.get("id") or "").strip()
    return f"{name}:{tc_id}" if tc_id else name


async def _openai_stream(
    messages: List[dict],
    system: Optional[str],
    agy_model: str,
    client_model: str,
    start_time: float,
    chat_id: str,
    chat_title: str,
    prompt_preview: str,
    api_key: str | None = None,
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[Any] = None,
    thought_as_text: Optional[bool] = None,
):
    response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    def _chunk(delta: dict, finish_reason=None):
        return {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": client_model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }

    yield f"data: {json.dumps(_chunk({'role': 'assistant'}))}\n\n"

    final_usage = {}
    assistant_chunks: List[str] = []
    emitted_tool_keys: set[str] = set()
    tool_call_idx = 0
    finish_reason = "stop"

    try:
        async for piece in with_heartbeat(
            stream_agy_completion(
                messages=messages,
                system=system,
                model=agy_model,
                tools=tools,
                tool_choice=tool_choice,
                thought_as_text=thought_as_text,
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
                    finish_reason = "tool_calls"
                    call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                    tool_name = tc.get("name", "")
                    tool_input = (
                        json.dumps(tc.get("input", {}))
                        if isinstance(tc.get("input"), dict)
                        else str(tc.get("input") or "{}")
                    )

                    delta_tool = {
                        "tool_calls": [
                            {
                                "index": tool_call_idx,
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": tool_input,
                                },
                            }
                        ]
                    }
                    tool_call_idx += 1
                    yield f"data: {json.dumps(_chunk(delta_tool))}\n\n"
            if "delta" in piece:
                assistant_chunks.append(piece["delta"])
                yield f"data: {json.dumps(_chunk({'content': piece['delta']}))}\n\n"
            if "usage" in piece:
                final_usage = piece.get("usage", {})
                if piece.get("tool_calls"):
                    for tc in piece["tool_calls"]:
                        tool_key = _tool_dedupe_key(tc)
                        if tool_key in emitted_tool_keys:
                            continue
                        emitted_tool_keys.add(tool_key)
                        finish_reason = "tool_calls"
                        call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                        tool_name = tc.get("name", "")
                        tool_input = (
                            json.dumps(tc.get("input", {}))
                            if isinstance(tc.get("input"), dict)
                            else str(tc.get("input") or "{}")
                        )

                        delta_tool = {
                            "tool_calls": [
                                {
                                    "index": tool_call_idx,
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": tool_input,
                                    },
                                }
                            ]
                        }
                        tool_call_idx += 1
                        yield f"data: {json.dumps(_chunk(delta_tool))}\n\n"
    except Exception as e:
        err_str = str(e)
        out_tokens = max(1, len(err_str) // 4)
        trace = get_current_trace()
        await stats_store.record_request(
            endpoint="openai-chat",
            model=client_model,
            pool_account=(trace.pool_account if trace and trace.pool_account else pool_manager.get_active_account_id()),
            prompt_tokens=0,
            completion_tokens=out_tokens,
            cache_tokens=0,
            success=False,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=type(e).__name__,
            chat_id=chat_id,
            chat_title=chat_title,
            prompt_preview=prompt_preview,
            response_preview=f"Error: {err_str}",
            raw_request=trace.raw_request_str if trace else None,
            raw_response=trace.raw_response_str if trace else None,
            response_status=trace.response_status if trace and trace.response_status is not None else 500,
        )
        if not assistant_chunks:
            raise
        yield f"data: {json.dumps(_chunk({'content': f'Error: {err_str}'}))}\n\n"
        yield f"data: {json.dumps(_chunk({}, finish_reason='stop'))}\n\n"
        yield "data: [DONE]\n\n"
        return

    assistant_text = "".join(assistant_chunks)
    final_prompt_len = sum(len(m.get("content") or "") for m in messages)
    usage = _usage_from_agy(final_usage, final_prompt_len, len(assistant_text))
    trace = get_current_trace()
    await stats_store.record_request(
        endpoint="openai-chat",
        model=client_model,
        pool_account=(trace.pool_account if trace and trace.pool_account else pool_manager.get_active_account_id()),
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cache_tokens=usage.cache_tokens,
        success=True,
        latency_ms=int((time.time() - start_time) * 1000),
        error_type=None,
        chat_id=chat_id,
        chat_title=chat_title,
        prompt_preview=prompt_preview,
        response_preview=assistant_text[:1500] if assistant_text else f"[{len(emitted_tool_keys)} tool calls]",
        raw_request=trace.raw_request_str if trace else None,
        raw_response=trace.raw_response_str if trace else None,
        response_status=trace.response_status if trace and trace.response_status is not None else 200,
    )
    record_key_output_tokens(api_key, usage.completion_tokens)
    yield f"data: {json.dumps(_chunk({}, finish_reason=finish_reason))}\n\n"
    yield "data: [DONE]\n\n"


@router.post(
    "/chat/completions",
    response_model=None,
    summary="Chat Completions",
    description="Creates a model response for the given chat conversation. Supports multimodal inputs via base64 data URIs.",
)
async def chat_completions(
    req: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    api_key: str = Depends(get_api_key),
):
    logger.info(f"Processing chat completions for model: {req.model}")
    start_time = time.time()
    start_trace()
    file_mgr = TempFileManager()
    background_tasks.add_task(file_mgr.cleanup)

    files_to_attach = []
    messages = []
    system_parts: List[str] = []
    for msg in req.messages:
        if msg.role == "system":
            if isinstance(msg.content, str):
                system_parts.append(msg.content)
            elif isinstance(msg.content, list):
                system_parts.append(" ".join(p.get("text", "") for p in msg.content if p.get("type") == "text"))
            continue

        content_text, msg_images = _extract_message_content_and_images(msg, file_mgr, files_to_attach)
        m_entry = {"role": msg.role, "content": content_text}
        if msg_images:
            m_entry["images"] = msg_images
        messages.append(m_entry)

    system_text = "\n\n".join(system_parts) if system_parts else None

    chat_id, chat_title, prompt_preview = stats_store.extract_chat_metadata(
        headers=dict(request.headers),
        messages=messages,
    )

    agy_model = await resolve_backend_model(req.model)
    display_model = (
        f"{req.model} · {resolve_http_model(agy_model)[0]} · {os.environ.get('AGY_HTTP_MAX_OUTPUT_TOKENS', '8192')}"
    )
    if get_force_model():
        logger.info(f"Force model: requested={req.model} backend={agy_model}")

    # Convert OpenAI tools format to Anthropic/internal format if provided
    converted_tools = None
    if req.tools:
        converted_tools = []
        for t in req.tools:
            if t.get("type") == "function" and "function" in t:
                fn = t["function"]
                converted_tools.append(
                    {
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    }
                )
            elif "name" in t:
                converted_tools.append(t)

    thought_param = req.thought_as_text if req.thought_as_text is not None else req.include_thoughts

    if req.stream:
        return StreamingResponse(
            _openai_stream(
                messages=messages,
                system=system_text,
                agy_model=agy_model,
                client_model=display_model,
                start_time=start_time,
                chat_id=chat_id,
                chat_title=chat_title,
                prompt_preview=prompt_preview,
                api_key=api_key,
                tools=converted_tools,
                tool_choice=req.tool_choice,
                thought_as_text=thought_param,
            ),
            media_type="text/event-stream",
        )

    if not req.stream:
        cached = get_cached_response(req.model, messages, req.temperature)
        if cached:
            return JSONResponse(content=cached)

    try:
        agy_response = await run_completion(
            messages=messages,
            system=system_text,
            model=agy_model,
            tools=converted_tools,
            tool_choice=req.tool_choice,
            thought_as_text=thought_param,
        )
    except Exception as e:
        trace = get_current_trace()
        await stats_store.record_request(
            endpoint="openai-chat",
            model=display_model,
            pool_account=(trace.pool_account if trace and trace.pool_account else pool_manager.get_active_account_id()),
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
            raw_request=trace.raw_request_str if trace else None,
            raw_response=trace.raw_response_str if trace else None,
            response_status=trace.response_status if trace and trace.response_status is not None else 500,
        )
        raise

    assistant_text = ""
    tool_calls = None
    finish_reason = "stop"

    if isinstance(agy_response, dict):
        assistant_text = agy_response.get("text") or agy_response.get("content") or agy_response.get("response") or ""
        if agy_response.get("tool_calls"):
            finish_reason = "tool_calls"
            tool_calls = []
            for tc in agy_response["tool_calls"]:
                tool_input = (
                    json.dumps(tc.get("input", {}))
                    if isinstance(tc.get("input"), dict)
                    else str(tc.get("input") or "{}")
                )
                tool_calls.append(
                    {
                        "id": tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": tool_input,
                        },
                    }
                )
    else:
        assistant_text = str(agy_response)

    agy_usage = agy_response.get("usage") if isinstance(agy_response, dict) else None
    final_prompt_len = sum(len(m.get("content") or "") for m in messages)
    usage = _usage_from_agy(agy_usage, final_prompt_len, len(assistant_text))

    trace = get_current_trace()
    await stats_store.record_request(
        endpoint="openai-chat",
        model=display_model,
        pool_account=(trace.pool_account if trace and trace.pool_account else pool_manager.get_active_account_id()),
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cache_tokens=usage.cache_tokens,
        success=True,
        latency_ms=int((time.time() - start_time) * 1000),
        error_type=None,
        chat_id=chat_id,
        chat_title=chat_title,
        prompt_preview=prompt_preview,
        response_preview=assistant_text[:1500] if assistant_text else f"[{len(tool_calls or [])} tool calls]",
        raw_request=trace.raw_request_str if trace else None,
        raw_response=trace.raw_response_str if trace else None,
        response_status=trace.response_status if trace and trace.response_status is not None else 200,
    )
    record_key_output_tokens(api_key, usage.completion_tokens)

    choice_msg = ChoiceMessage(content=assistant_text or None, tool_calls=tool_calls)
    response = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=req.model,
        choices=[Choice(message=choice_msg, finish_reason=finish_reason)],
        usage=usage,
    )
    resp_dict = response.model_dump()
    put_cached_response(req.model, messages, resp_dict, req.temperature)
    return response
