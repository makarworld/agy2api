import time
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, BackgroundTasks
from pydantic import BaseModel
from app.api.models import ChatCompletionRequest, ChatCompletionResponse, Choice, ChoiceMessage, Usage, ModelList, Model
from app.core.security import get_api_key
from app.core.agy_runner import run_agy_prompt
from app.core.file_handler import TempFileManager

router = APIRouter()

class ImageGenerationRequest(BaseModel):
    prompt: str
    n: Optional[int] = 1
    size: Optional[str] = "1024x1024"
    response_format: Optional[str] = "url"

class ImageObject(BaseModel):
    url: Optional[str] = None
    b64_json: Optional[str] = None

class ImageGenerationResponse(BaseModel):
    created: int
    data: List[ImageObject]

@router.get("/models", response_model=ModelList)
async def list_models(api_key: str = Depends(get_api_key)):
    models = [
        Model(id="Gemini 3.6 Flash (High)", created=int(time.time())),
        Model(id="Gemini 3.1 Pro (High)", created=int(time.time()))
    ]
    return ModelList(data=models)

@router.post("/chat/completions", response_model=ChatCompletionResponse)
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

@router.post("/images/generations", response_model=ImageGenerationResponse)
async def generate_image(req: ImageGenerationRequest, api_key: str = Depends(get_api_key)):
    # We instruct AGY to generate an image and return the path/base64 in JSON format
    # Usually this invokes a skill like `ak:ai-artist` or similar.
    # We will formulate a strict prompt to agy.
    prompt = f"Generate an image for the following prompt: '{req.prompt}'. Return ONLY the absolute local file path of the generated image in your response, do not include any other conversational text."
    
    agy_response = await run_agy_prompt(prompt=prompt, output_format="json")
    
    # Extract path
    image_path = ""
    if isinstance(agy_response, dict):
        image_path = agy_response.get("text") or agy_response.get("content") or agy_response.get("response") or str(agy_response)
    else:
        image_path = str(agy_response)
        
    # Since we can't easily return local paths if the client is remote, we can base64 encode it
    # If the file exists locally, we read it
    image_path = image_path.strip()
    img_data = ImageObject(url=image_path) # Default to just giving the path as URL
    
    import os
    if os.path.exists(image_path) and os.path.isfile(image_path):
        import base64
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            if req.response_format == "b64_json":
                img_data = ImageObject(b64_json=b64)
            else:
                # We could host it, but for simplicity we can return data uri in url
                img_data = ImageObject(url=f"data:image/png;base64,{b64}")

    return ImageGenerationResponse(
        created=int(time.time()),
        data=[img_data]
    )

