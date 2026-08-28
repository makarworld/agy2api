import io
import json
import logging
import os
import subprocess
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
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
from app.core.agy_runner import (
    run_agy_prompt,
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
)
from app.core.security import get_api_key

logger = logging.getLogger(__name__)

router = APIRouter()
capcut_wrapper = AsyncCapCutWrapper()


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(
        ...,
        description="A text description of the desired image(s). (Tips: You can include desired aspect ratios here like 9:16 or 16:9)",
    )
    n: int | None = Field(1, description="The number of images to generate")
    response_format: str | None = Field(
        "url",
        description="The format in which the generated images are returned. Must be one of url or b64_json",
    )
    reference_images: list[str] | None = Field(
        None,
        description="Optional list of base64 data URIs to use as reference images.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "A cute orange cat playing with a ball of yarn, cartoon style, tỉ lệ 9:16",
                    "n": 1,
                    "response_format": "url",
                }
            ]
        }
    }


class ImageObject(BaseModel):
    url: str | None = None
    b64_json: str | None = None


class ImageGenerationResponse(BaseModel):
    created: int
    data: list[ImageObject]


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


def _usage_from_agy(
    agy_usage: dict | None, fallback_prompt_len: int, fallback_completion_len: int
) -> Usage:
    # agy's own JSON payload carries real token usage (confirmed live: input_tokens,
    # output_tokens, thinking_tokens, cache_read_tokens, total_tokens). Fall back to a
    # character-count heuristic only if that field is ever missing.
    if isinstance(agy_usage, dict) and agy_usage:
        prompt_tokens = agy_usage.get("input_tokens", 0)
        completion_tokens = agy_usage.get("output_tokens", 0) + agy_usage.get(
            "thinking_tokens", 0
        )
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


async def _openai_stream(
    messages: list[dict],
    agy_model: str,
    client_model: str,
    start_time: float,
    chat_id: str,
    chat_title: str,
    prompt_preview: str,
    api_key: str | None = None,
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
    assistant_chunks: list[str] = []
    try:
        async for piece in with_heartbeat(
            stream_agy_completion(messages=messages, model=agy_model)
        ):
            if piece is None:
                yield ": ping\n\n"
                continue
            if "delta" in piece:
                assistant_chunks.append(piece["delta"])
                yield f"data: {json.dumps(_chunk({'content': piece['delta']}))}\n\n"
            if "usage" in piece:
                final_usage = piece.get("usage", {})
    except Exception as e:
        await stats_store.record_request(
            endpoint="openai-chat",
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
        yield f"data: {json.dumps(_chunk({}, finish_reason='error'))}\n\n"
        yield "data: [DONE]\n\n"
        return

    assistant_text = "".join(assistant_chunks)
    final_prompt_len = sum(len(m["content"]) for m in messages)
    usage = _usage_from_agy(final_usage, final_prompt_len, len(assistant_text))
    await stats_store.record_request(
        endpoint="openai-chat",
        model=client_model,
        pool_account=pool_manager.get_active_account_id(),
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cache_tokens=usage.cache_tokens,
        success=True,
        latency_ms=int((time.time() - start_time) * 1000),
        error_type=None,
        chat_id=chat_id,
        chat_title=chat_title,
        prompt_preview=prompt_preview,
        response_preview=assistant_text[:1500],
    )
    record_key_output_tokens(api_key, usage.completion_tokens)
    yield f"data: {json.dumps(_chunk({}, finish_reason='stop'))}\n\n"
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
    file_mgr = TempFileManager()
    background_tasks.add_task(file_mgr.cleanup)

    files_to_attach = []
    messages = []
    for msg in req.messages:
        content_text, msg_images = _extract_message_content_and_images(
            msg, file_mgr, files_to_attach
        )
        m_entry = {"role": msg.role, "content": content_text}
        if msg_images:
            m_entry["images"] = msg_images
        messages.append(m_entry)

    chat_id, chat_title, prompt_preview = stats_store.extract_chat_metadata(
        headers=dict(request.headers),
        messages=messages,
    )

    agy_model = await resolve_backend_model(req.model)
    if get_force_model():
        logger.info(f"Force model: requested={req.model} backend={agy_model}")

    if req.stream:
        return StreamingResponse(
            _openai_stream(
                messages,
                agy_model,
                req.model,
                start_time,
                chat_id,
                chat_title,
                prompt_preview,
                api_key=api_key,
            ),
            media_type="text/event-stream",
        )

    try:
        agy_response = await run_completion(messages=messages, model=agy_model)
    except Exception as e:
        await stats_store.record_request(
            endpoint="openai-chat",
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
        raise

    assistant_text = ""
    if isinstance(agy_response, dict):
        assistant_text = (
            agy_response.get("text")
            or agy_response.get("content")
            or agy_response.get("response")
            or str(agy_response)
        )
    else:
        assistant_text = str(agy_response)

    agy_usage = agy_response.get("usage") if isinstance(agy_response, dict) else None
    final_prompt_len = sum(len(m["content"]) for m in messages)
    usage = _usage_from_agy(agy_usage, final_prompt_len, len(assistant_text))

    await stats_store.record_request(
        endpoint="openai-chat",
        model=req.model,
        pool_account=pool_manager.get_active_account_id(),
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cache_tokens=usage.cache_tokens,
        success=True,
        latency_ms=int((time.time() - start_time) * 1000),
        error_type=None,
        chat_id=chat_id,
        chat_title=chat_title,
        prompt_preview=prompt_preview,
        response_preview=assistant_text[:1500],
    )
    record_key_output_tokens(api_key, usage.completion_tokens)

    response = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=req.model,
        choices=[Choice(message=ChoiceMessage(content=assistant_text))],
        usage=usage,
    )
    return response


@router.post(
    "/images/generations",
    response_model=ImageGenerationResponse,
    summary="Image Generations",
    description="Creates an image given a prompt using the AGY artist skills.",
)
async def generate_image(
    req: ImageGenerationRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    api_key: str = Depends(get_api_key),
):
    logger.info(f"Generating image. Prompt: {req.prompt[:50]}...")
    start_time = time.time()
    file_mgr = TempFileManager()
    background_tasks.add_task(file_mgr.cleanup)

    ref_paths = []
    if req.reference_images:
        for url in req.reference_images:
            if url.startswith("data:"):
                ext = ".png"
                if "jpeg" in url or "jpg" in url:
                    ext = ".jpg"
                try:
                    fpath = file_mgr.add_base64_file(url, ext=ext)
                    ref_paths.append(fpath)
                except Exception:
                    pass

    prompt = f"Generate an image for the following prompt: '{req.prompt}'. Return ONLY the absolute local file path of the generated image in your response, do not include any other conversational text."

    if ref_paths:
        paths_str = ", ".join([f"'{p}'" for p in ref_paths])
        prompt = f"Use the reference images at {paths_str} to generate an image for the following prompt: '{req.prompt}'. Return ONLY the absolute local file path of the generated image in your response, do not include any other conversational text."

    import hashlib

    img_chat_id = (
        "img_"
        + hashlib.sha256(req.prompt.encode("utf-8", errors="replace")).hexdigest()[:12]
    )
    img_title = f"Image: {req.prompt.strip().replace(chr(10), ' ')[:80]}"

    try:
        agy_response = await run_agy_prompt(prompt=prompt)
    except Exception as e:
        await stats_store.record_request(
            endpoint="image-generation",
            model="artist",
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=max(1, len(req.prompt) // 4),
            completion_tokens=0,
            cache_tokens=0,
            success=False,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=type(e).__name__,
            chat_id=img_chat_id,
            chat_title=img_title,
            prompt_preview=req.prompt[:1000],
            response_preview=f"Error: {str(e)}",
        )
        raise

    image_path = ""
    if isinstance(agy_response, dict):
        image_path = (
            agy_response.get("text")
            or agy_response.get("content")
            or agy_response.get("response")
            or str(agy_response)
        )
    else:
        image_path = str(agy_response)

    image_path = image_path.strip()
    img_data = ImageObject(url=image_path)

    import os

    if os.path.exists(image_path) and os.path.isfile(image_path):
        import base64

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            if req.response_format == "b64_json":
                img_data = ImageObject(b64_json=b64)
            else:
                img_data = ImageObject(url=f"data:image/png;base64,{b64}")

        def remove_file(path):
            try:
                os.remove(path)
            except Exception:
                pass

        background_tasks.add_task(remove_file, image_path)

    await stats_store.record_request(
        endpoint="image-generation",
        model="artist",
        pool_account=pool_manager.get_active_account_id(),
        prompt_tokens=max(1, len(req.prompt) // 4),
        completion_tokens=100,
        cache_tokens=0,
        success=True,
        latency_ms=int((time.time() - start_time) * 1000),
        error_type=None,
        chat_id=img_chat_id,
        chat_title=img_title,
        prompt_preview=req.prompt[:1000],
        response_preview=f"Generated image: {image_path[:200]}",
    )

    return ImageGenerationResponse(created=int(time.time()), data=[img_data])


@router.post("/auth/verify", summary="Verify admin password / API key")
async def verify_auth(api_key: str = Depends(get_api_key)):
    return {"status": "ok", "authenticated": True}


def _read_local_log_tail(lines: int) -> str:
    log_path = os.environ.get("AGY_LOG_FILE_PATH", "app/data/agy2api.log")
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        if not all_lines:
            return "Log file is empty."
        return "".join(all_lines[-lines:])
    except FileNotFoundError:
        return "No log file found yet."


@router.get(
    "/logs",
    summary="Get System Logs",
    description="Read the latest system logs of the AGY Wrapper service.",
)
async def get_logs(lines: int = 100, api_key: str = Depends(get_api_key)):
    try:
        result = subprocess.run(
            [
                "journalctl",
                "--user",
                "-u",
                "agy-wrapper.service",
                "-n",
                str(lines),
                "--no-pager",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return {"logs": result.stdout}
        # journalctl exists but failed (e.g. not running under systemd) -- fall back to the local file
        return {"logs": _read_local_log_tail(lines)}
    except FileNotFoundError:
        # journalctl isn't installed at all (e.g. local dev on Windows)
        return {"logs": _read_local_log_tail(lines)}
    except Exception as e:
        return {"logs": f"Error reading logs: {str(e)}"}


@router.post(
    "/audio/speech",
    summary="Text to Speech (Audio Generations)",
    description="Tạo tệp âm thanh từ văn bản dựa trên chuẩn OpenAI Audio API (engine CapCut).",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Binary stream của file MP3 (audio/mpeg)",
            "content": {"audio/mpeg": {}},
        }
    },
)
async def audio_speech(
    req: SpeechRequest, request: Request, api_key: str = Depends(get_api_key)
):
    logger.info(
        f"Generating speech (voice={req.voice}, speed={req.speed}). Text: {req.input[:50]}..."
    )
    start_time = time.time()
    import hashlib

    tts_chat_id = (
        "tts_"
        + hashlib.sha256(req.input.encode("utf-8", errors="replace")).hexdigest()[:12]
    )
    tts_title = f"TTS: {req.input.strip().replace(chr(10), ' ')[:80]}"
    try:
        audio_bytes = await capcut_wrapper.generate_speech(
            text=req.input, voice=req.voice, speed=req.speed
        )
        await stats_store.record_request(
            endpoint="audio-speech",
            model=req.model,
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=max(1, len(req.input) // 4),
            completion_tokens=len(audio_bytes) // 100,
            cache_tokens=0,
            success=True,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=None,
            chat_id=tts_chat_id,
            chat_title=tts_title,
            prompt_preview=req.input[:1000],
            response_preview=f"Audio generated ({req.voice}, {req.speed}x, {len(audio_bytes)} bytes)",
        )
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
    except Exception as e:
        await stats_store.record_request(
            endpoint="audio-speech",
            model=req.model,
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=max(1, len(req.input) // 4),
            completion_tokens=0,
            cache_tokens=0,
            success=False,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=type(e).__name__,
            chat_id=tts_chat_id,
            chat_title=tts_title,
            prompt_preview=req.input[:1000],
            response_preview=f"Error: {str(e)}",
        )
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get(
    "/audio/voices",
    summary="List Voices",
    description="Lấy danh sách tất cả các giọng đọc (voices) khả dụng từ engine CapCut.",
)
async def audio_voices(api_key: str = Depends(get_api_key)):
    try:
        voices = capcut_wrapper.get_voices()
        return JSONResponse(content={"voices": voices})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post(
    "/audio/transcriptions",
    summary="Speech to Text (Audio Transcriptions)",
    description="Chuyển đổi file âm thanh thành văn bản hoặc phụ đề thời gian chuẩn.",
)
async def audio_transcriptions(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(
        ..., description="Tệp âm thanh cần upload (mp3, mp4, wav, v.v...)"
    ),
    model: str = Form("whisper-1", description="ID của mô hình (vd: whisper-1)"),
    language: str = Form(
        None, description="Mã ngôn ngữ (vd: en-US, vi-VN). Bỏ trống để tự nhận diện."
    ),
    response_format: str = Form(
        "json", description="Định dạng trả về (json, text, srt, vtt)"
    ),
    api_key: str = Depends(get_api_key),
):
    logger.info(
        f"Transcribing audio file: {file.filename}, language: {language}, format: {response_format}"
    )
    start_time = time.time()
    stt_chat_id = "stt_" + uuid.uuid4().hex[:12]
    stt_title = f"STT: {file.filename or 'Audio transcription'}"
    try:
        file_mgr = TempFileManager()
        background_tasks.add_task(file_mgr.cleanup)

        import os

        ext = os.path.splitext(file.filename)[1] if file.filename else ".mp3"
        temp_path = os.path.join(file_mgr.temp_dir.name, f"upload{ext}")
        with open(temp_path, "wb") as f:
            f.write(await file.read())

        transcription = await capcut_wrapper.transcribe_audio(
            file_path=temp_path, response_format=response_format, language=language
        )

        await stats_store.record_request(
            endpoint="audio-transcription",
            model=model,
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=50,
            completion_tokens=max(1, len(transcription) // 4),
            cache_tokens=0,
            success=True,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=None,
            chat_id=stt_chat_id,
            chat_title=stt_title,
            prompt_preview=f"Transcribe: {file.filename}",
            response_preview=transcription[:1500],
        )

        if response_format in ["json", "verbose_json"]:
            import json

            return JSONResponse(content=json.loads(transcription))
        else:
            return Response(content=transcription, media_type="text/plain")
    except Exception as e:
        await stats_store.record_request(
            endpoint="audio-transcription",
            model=model,
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=50,
            completion_tokens=0,
            cache_tokens=0,
            success=False,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=type(e).__name__,
            chat_id=stt_chat_id,
            chat_title=stt_title,
            prompt_preview=f"Transcribe: {file.filename}",
            response_preview=f"Error: {str(e)}",
        )
        return JSONResponse(status_code=500, content={"error": str(e)})
