import time
import uuid
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response, JSONResponse
from pydantic import BaseModel, Field
from app.api.models import ChatCompletionRequest, ChatCompletionResponse, Choice, ChoiceMessage, Usage, ModelList, Model, SpeechRequest
from app.core.security import get_api_key
from app.core.agy_runner import run_agy_prompt
from app.core.file_handler import TempFileManager
from app.core.capcut_api import AsyncCapCutWrapper

router = APIRouter()
capcut_wrapper = AsyncCapCutWrapper()

class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., description="A text description of the desired image(s). (Tips: You can include desired aspect ratios here like 9:16 or 16:9)")
    n: Optional[int] = Field(1, description="The number of images to generate")
    response_format: Optional[str] = Field("url", description="The format in which the generated images are returned. Must be one of url or b64_json")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "A cute orange cat playing with a ball of yarn, cartoon style, tỉ lệ 9:16",
                    "n": 1,
                    "response_format": "url"
                }
            ]
        }
    }

class ImageObject(BaseModel):
    url: Optional[str] = None
    b64_json: Optional[str] = None

class ImageGenerationResponse(BaseModel):
    created: int
    data: List[ImageObject]

@router.get("/models", response_model=ModelList, summary="List Models", description="Returns a list of available AI models.")
async def list_models(api_key: str = Depends(get_api_key)):
    models = [
        Model(id="Gemini 3.6 Flash (High)", created=int(time.time())),
        Model(id="Gemini 3.1 Pro (High)", created=int(time.time()))
    ]
    return ModelList(data=models)

@router.post("/chat/completions", response_model=ChatCompletionResponse, summary="Chat Completions", description="Creates a model response for the given chat conversation. Supports multimodal inputs via base64 data URIs.")
async def chat_completions(req: ChatCompletionRequest, background_tasks: BackgroundTasks, api_key: str = Depends(get_api_key)):
    file_mgr = TempFileManager()
    background_tasks.add_task(file_mgr.cleanup)
    
    prompt_lines = []
    files_to_attach = []
    
    for msg in req.messages:
        if isinstance(msg.content, str):
            prompt_lines.append(f"{msg.role.capitalize()}: {msg.content}")
        elif isinstance(msg.content, list):
            # Parse mixed content (text + image_url)
            text_parts = []
            for p in msg.content:
                if p.get("type") == "text":
                    text_parts.append(p.get("text", ""))
                elif p.get("type") == "image_url":
                    url = p.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        # Extract extension roughly
                        ext = ".png"
                        if "jpeg" in url or "jpg" in url: ext = ".jpg"
                        try:
                            fpath = file_mgr.add_base64_file(url, ext=ext)
                            files_to_attach.append(fpath)
                            text_parts.append(f"[Attached Image: {fpath}]")
                        except Exception as e:
                            text_parts.append(f"[Failed to attach image: {e}]")
                    else:
                        text_parts.append(f"[Image URL: {url}]")
            prompt_lines.append(f"{msg.role.capitalize()}: {' '.join(text_parts)}")
            
    prompt_lines.append("Assistant: ")
    final_prompt = "\n".join(prompt_lines)
    
    # We pass the files list to agy_runner if we want to use --add-dir or something similar,
    # but since we already injected paths into the prompt, agy's vision might pick it up automatically if it can read local files.
    agy_response = await run_agy_prompt(prompt=final_prompt, model=req.model, files=files_to_attach)
    
    assistant_text = ""
    if isinstance(agy_response, dict):
        assistant_text = agy_response.get("text") or agy_response.get("content") or agy_response.get("response") or str(agy_response)
    else:
        assistant_text = str(agy_response)
        
    response = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=req.model,
        choices=[Choice(message=ChoiceMessage(content=assistant_text))],
        usage=Usage()
    )
    return response

@router.post("/images/generations", response_model=ImageGenerationResponse, summary="Image Generations", description="Creates an image given a prompt using the AGY artist skills.")
async def generate_image(req: ImageGenerationRequest, background_tasks: BackgroundTasks, api_key: str = Depends(get_api_key)):
    # We instruct AGY to generate an image and return the path/base64 in JSON format
    prompt = f"Generate an image for the following prompt: '{req.prompt}'. Return ONLY the absolute local file path of the generated image in your response, do not include any other conversational text."
    
    agy_response = await run_agy_prompt(prompt=prompt, output_format="json")
    
    # Extract path
    image_path = ""
    if isinstance(agy_response, dict):
        image_path = agy_response.get("text") or agy_response.get("content") or agy_response.get("response") or str(agy_response)
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
                
        # Schedule cleanup of the generated image file after returning the response
        def remove_file(path):
            try:
                os.remove(path)
            except Exception:
                pass
        
        background_tasks.add_task(remove_file, image_path)

    return ImageGenerationResponse(
        created=int(time.time()),
        data=[img_data]
    )

import subprocess

@router.get("/logs", summary="Get System Logs", description="Read the latest system logs of the AGY Wrapper service.")
async def get_logs(lines: int = 100, api_key: str = Depends(get_api_key)):
    try:
        result = subprocess.run(
            ["journalctl", "-u", "agy-wrapper.service", "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return {"logs": result.stdout}
        else:
            return {"logs": f"Failed to read logs (code {result.returncode}): {result.stderr}"}
    except Exception as e:
        return {"logs": f"Error reading logs: {str(e)}"}

@router.post("/audio/speech", summary="Text to Speech", description="Generates audio from the input text.")
async def audio_speech(req: SpeechRequest, api_key: str = Depends(get_api_key)):
    try:
        audio_bytes = await capcut_wrapper.generate_speech(
            text=req.input,
            voice=req.voice,
            speed=req.speed
        )
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/audio/voices", summary="List Voices", description="Returns a list of all available CapCut voices.")
async def audio_voices(api_key: str = Depends(get_api_key)):
    try:
        voices = capcut_wrapper.get_voices()
        return JSONResponse(content={"voices": voices})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.post("/audio/transcriptions", summary="Speech to Text", description="Transcribes audio into the input language.")
async def audio_transcriptions(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    language: str = Form("en-US"),
    response_format: str = Form("json"),
    api_key: str = Depends(get_api_key)
):
    try:
        file_mgr = TempFileManager()
        background_tasks.add_task(file_mgr.cleanup)
        
        import os
        ext = os.path.splitext(file.filename)[1] if file.filename else ".mp3"
        temp_path = os.path.join(file_mgr.temp_dir.name, f"upload{ext}")
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        transcription = await capcut_wrapper.transcribe_audio(
            file_path=temp_path,
            response_format=response_format,
            language=language
        )
        
        if response_format in ["json", "verbose_json"]:
            import json
            return JSONResponse(content=json.loads(transcription))
        else:
            return Response(content=transcription, media_type="text/plain")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
