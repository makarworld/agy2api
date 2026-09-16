import base64
import hashlib
import logging
import os
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core import agy_http_client, pool_manager, stats_store
from app.core.file_handler import TempFileManager
from app.core.request_tracer import get_current_trace, start_trace
from app.core.security import get_optional_api_key

logger = logging.getLogger(__name__)

router = APIRouter()


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(
        ...,
        description="A text description of the desired image(s). (Tips: You can include desired aspect ratios here like 9:16 or 16:9)",
    )
    model: str | None = Field(None, description="Image model name override (default gemini-3.1-flash-image)")
    n: int | None = Field(1, description="The number of images to generate")
    size: str | None = Field(None, description="Image aspect ratio or size, e.g. 1:1, 4:3, 16:9, 9:16")
    response_format: str | None = Field(
        "url",
        description="The format in which the generated images are returned. Must be one of url, b64_json or binary",
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


class SimpleImageRequest(BaseModel):
    prompt: str = Field(..., description="Prompt description for image generation")
    model: str | None = Field(None, description="Image model name")
    size: str | None = Field(None, description="Aspect ratio or size (e.g. 1:1, 4:3, 16:9, 9:16)")
    format: str | None = Field("url", description="Response format: url, b64_json or binary")


async def _process_image_generation(
    prompt: str,
    *,
    model: str | None = None,
    size: str | None = None,
    response_format: str | None = "url",
    reference_images: list[str] | None = None,
    background_tasks: BackgroundTasks | None = None,
    api_key: str | None = None,
):
    start_time = time.time()
    start_trace()
    file_mgr = TempFileManager()
    if background_tasks:
        background_tasks.add_task(file_mgr.cleanup)

    ref_paths = []
    if reference_images:
        for url in reference_images:
            if url.startswith("data:"):
                ext = ".png"
                if "jpeg" in url or "jpg" in url:
                    ext = ".jpg"
                try:
                    fpath = file_mgr.add_base64_file(url, ext=ext)
                    ref_paths.append(fpath)
                except Exception:
                    pass

    reference_parts: list[dict] = []
    for path in ref_paths:
        try:
            with open(path, "rb") as f:
                raw = f.read()
            ext = os.path.splitext(path)[1].lower()
            mime_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
            reference_parts.append(
                {
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": base64.b64encode(raw).decode("utf-8"),
                    }
                }
            )
        except Exception:
            pass

    target_model = model or agy_http_client.DEFAULT_IMAGE_MODEL
    img_chat_id = "img_" + hashlib.sha256(prompt.encode("utf-8", errors="replace")).hexdigest()[:12]
    img_title = f"Image: {prompt.strip().replace(chr(10), ' ')[:80]}"

    try:
        image_result = await agy_http_client.generate_image(
            prompt,
            model=target_model,
            size=size,
            reference_parts=reference_parts or None,
        )
    except Exception as e:
        trace = get_current_trace()
        await stats_store.record_request(
            endpoint="image-generation",
            model=target_model,
            pool_account=(trace.pool_account if trace and trace.pool_account else pool_manager.get_active_account_id()),
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=0,
            cache_tokens=0,
            success=False,
            latency_ms=int((time.time() - start_time) * 1000),
            error_type=type(e).__name__,
            chat_id=img_chat_id,
            chat_title=img_title,
            prompt_preview=prompt[:1000],
            response_preview=f"Error: {str(e)}",
            raw_request=trace.raw_request_str if trace else None,
            raw_response=trace.raw_response_str if trace else None,
            response_status=trace.response_status if trace and trace.response_status is not None else 500,
        )
        if "HTTP 429" in str(e):
            raise HTTPException(status_code=429, detail=f"Image generation rate limit: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    b64 = image_result.get("data") or ""
    mime_type = image_result.get("mime_type", "image/jpeg")

    trace = get_current_trace()
    await stats_store.record_request(
        endpoint="image-generation",
        model=target_model,
        pool_account=(trace.pool_account if trace and trace.pool_account else pool_manager.get_active_account_id()),
        prompt_tokens=max(1, len(prompt) // 4),
        completion_tokens=100,
        cache_tokens=0,
        success=True,
        latency_ms=int((time.time() - start_time) * 1000),
        error_type=None,
        chat_id=img_chat_id,
        chat_title=img_title,
        prompt_preview=prompt[:1000],
        response_preview="Generated image via HTTP",
        raw_request=trace.raw_request_str if trace else None,
        raw_response=trace.raw_response_str if trace else None,
        response_status=trace.response_status if trace and trace.response_status is not None else 200,
    )

    if response_format == "binary":
        raw_bytes = base64.b64decode(b64)
        return Response(content=raw_bytes, media_type=mime_type)

    if response_format == "b64_json":
        img_data = ImageObject(b64_json=b64)
    else:
        img_data = ImageObject(url=f"data:{mime_type};base64,{b64}")

    return ImageGenerationResponse(created=int(time.time()), data=[img_data])


@router.post(
    "/images/generations",
    summary="Image Generations (OpenAI Compatible)",
    description="Creates an image given a prompt. Auth is optional (API key or public).",
)
async def generate_image(
    req: ImageGenerationRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    api_key: str | None = Depends(get_optional_api_key),
):
    logger.info(f"Generating image. Prompt: {req.prompt[:50]}...")
    return await _process_image_generation(
        prompt=req.prompt,
        model=req.model,
        size=req.size,
        response_format=req.response_format,
        reference_images=req.reference_images,
        background_tasks=background_tasks,
        api_key=api_key,
    )


@router.get(
    "/image",
    summary="Simple Image Generation (GET)",
    description="Generate image by passing prompt via query string. Auth is optional. Format can be binary, url, b64_json.",
)
async def generate_image_simple_get(
    prompt: str,
    background_tasks: BackgroundTasks,
    model: str | None = None,
    size: str | None = None,
    format: str | None = "binary",
    api_key: str | None = Depends(get_optional_api_key),
):
    return await _process_image_generation(
        prompt=prompt,
        model=model,
        size=size,
        response_format=format,
        background_tasks=background_tasks,
        api_key=api_key,
    )


@router.post(
    "/image",
    summary="Simple Image Generation (POST)",
    description="Generate image by passing {prompt: '...'} in JSON body. Auth is optional.",
)
async def generate_image_simple_post(
    req: SimpleImageRequest,
    background_tasks: BackgroundTasks,
    api_key: str | None = Depends(get_optional_api_key),
):
    return await _process_image_generation(
        prompt=req.prompt,
        model=req.model,
        size=req.size,
        response_format=req.format,
        background_tasks=background_tasks,
        api_key=api_key,
    )
