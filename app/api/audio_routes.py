import hashlib
import io
import logging
import os
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.models import SpeechRequest
from app.core import pool_manager, stats_store
from app.core.capcut_api import AsyncCapCutWrapper
from app.core.file_handler import TempFileManager
from app.core.security import get_api_key

logger = logging.getLogger(__name__)

router = APIRouter()
capcut_wrapper = AsyncCapCutWrapper()


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
async def audio_speech(req: SpeechRequest, request: Request, api_key: str = Depends(get_api_key)):
    logger.info(f"Generating speech (voice={req.voice}, speed={req.speed}). Text: {req.input[:50]}...")
    start_time = time.time()

    tts_chat_id = "tts_" + hashlib.sha256(req.input.encode("utf-8", errors="replace")).hexdigest()[:12]
    tts_title = f"TTS: {req.input.strip().replace(chr(10), ' ')[:80]}"
    try:
        audio_bytes = await capcut_wrapper.generate_speech(text=req.input, voice=req.voice, speed=req.speed)
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
            response_status=200,
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
            response_status=500,
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
    file: UploadFile = File(..., description="Tệp âm thanh cần upload (mp3, mp4, wav, v.v...)"),
    model: str = Form("whisper-1", description="ID của mô hình (vd: whisper-1)"),
    language: str = Form(None, description="Mã ngôn ngữ (vd: en-US, vi-VN). Bỏ trống để tự nhận diện."),
    response_format: str = Form("json", description="Định dạng trả về (json, text, srt, vtt)"),
    api_key: str = Depends(get_api_key),
):
    logger.info(f"Transcribing audio file: {file.filename}, language: {language}, format: {response_format}")
    start_time = time.time()
    stt_chat_id = "stt_" + uuid.uuid4().hex[:12]
    stt_title = f"STT: {file.filename or 'Audio transcription'}"
    try:
        file_mgr = TempFileManager()
        background_tasks.add_task(file_mgr.cleanup)

        ext = os.path.splitext(file.filename)[1] if file.filename else ".mp3"
        temp_path = os.path.join(file_mgr.temp_dir.name, f"upload{ext}")
        with open(temp_path, "wb") as f:
            f.write(await file.read())

        transcription = await capcut_wrapper.transcribe_audio(
            file_path=temp_path, response_format=response_format, language=language
        )
        await stats_store.record_request(
            endpoint="audio-transcriptions",
            model=model,
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=10,
            completion_tokens=len(transcription) // 4 if isinstance(transcription, str) else 20,
            cache_tokens=0,
            success=True,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=None,
            chat_id=stt_chat_id,
            chat_title=stt_title,
            prompt_preview=f"File: {file.filename} ({language or 'auto'})",
            response_preview=str(transcription)[:1000],
            response_status=200,
        )

        if response_format in ["json", "verbose_json"]:
            import json

            return JSONResponse(content=json.loads(transcription))
        else:
            return Response(content=transcription, media_type="text/plain")
    except Exception as e:
        await stats_store.record_request(
            endpoint="audio-transcriptions",
            model=model,
            pool_account=pool_manager.get_active_account_id(),
            prompt_tokens=10,
            completion_tokens=0,
            cache_tokens=0,
            success=False,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=type(e).__name__,
            chat_id=stt_chat_id,
            chat_title=stt_title,
            prompt_preview=f"File: {file.filename} ({language or 'auto'})",
            response_preview=f"Error: {str(e)}",
            response_status=500,
        )
        return JSONResponse(status_code=500, content={"error": str(e)})
