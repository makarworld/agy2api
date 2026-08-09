import asyncio
import json
import base64
import httpx
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Use the extracted capcut_tts_api module
from app.capcut_tts_api.client import CapCutClient
from app.capcut_tts_api.models import DeviceConfig

class AsyncCapCutWrapper:
    def __init__(self):
        # We can pass an empty DeviceConfig, the client will generate one with defaults
        self.device = DeviceConfig()
        self.client = CapCutClient(device=self.device)
        self.catalog_path = Path(__file__).parent.parent / "Voice.json"

    def resolve_voice(self, voice_name: str) -> str:
        # Map OpenAI voices to CapCut voices
        mapping = {
            "alloy": "BV074_streaming",
            "echo": "BV074_streaming",
            "fable": "BV074_streaming",
            "onyx": "BV074_streaming",
            "nova": "BV074_streaming",
            "shimmer": "BV074_streaming",
        }
        return mapping.get(voice_name.lower(), voice_name)

    def get_voices(self) -> list:
        if not self.catalog_path.exists():
            return []
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def generate_speech(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        voice_target = self.resolve_voice(voice)
        logger.info(f"Calling CapCut TTS with voice target: {voice_target}, speed: {speed}")
        
        # Run synchronous generate_speech in a background thread to avoid blocking FastAPI
        res = await asyncio.to_thread(
            self.client.generate_speech,
            texts=text,
            voice=voice_target,
            rate=str(speed),
            wait=True,
            poll_interval=1.0,
            timeout=60.0
        )
        
        tasks = (res.get("data") or {}).get("tasks") or []
        if not tasks:
            raise Exception("No task returned from CapCut API")
            
        raw_payload = tasks[0].get("payload", "{}")
        payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        
        audio_url = None
        if payload.get("audio"):
            return base64.b64decode(payload["audio"])
        elif payload.get("audio_url"):
            audio_url = payload.get("audio_url")
        elif payload.get("audio_subtitles") and len(payload["audio_subtitles"]) > 0:
            audio_url = payload["audio_subtitles"][0].get("speech_url") or payload["audio_subtitles"][0].get("url")

        if audio_url:
            async with httpx.AsyncClient() as client:
                r = await client.get(audio_url)
                r.raise_for_status()
                return r.content
                
        raise Exception(f"Audio not found in payload: {payload}")

    def _format_time(self, ms: int, sep: str = ",") -> str:
        h, r = divmod(ms, 3600000)
        m, r = divmod(r, 60000)
        s, ms_r = divmod(r, 1000)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int(ms_r):03d}"

    def _to_srt(self, subtitles) -> str:
        lines = []
        for i, u in enumerate(subtitles.utterances, 1):
            lines.append(str(i))
            lines.append(f"{self._format_time(u.start_time, ',')} --> {self._format_time(u.end_time, ',')}")
            lines.append(u.text)
            lines.append("")
        return "\n".join(lines)

    def _to_vtt(self, subtitles) -> str:
        lines = ["WEBVTT\n"]
        for i, u in enumerate(subtitles.utterances, 1):
            lines.append(str(i))
            lines.append(f"{self._format_time(u.start_time, '.')} --> {self._format_time(u.end_time, '.')}")
            lines.append(u.text)
            lines.append("")
        return "\n".join(lines)

    async def transcribe_audio(self, file_path: str, response_format: str = "json", language: str = "en-US") -> str:
        logger.info(f"Calling CapCut STT for file: {file_path}, language: {language}")
        # Run synchronous transcribe_file in a background thread
        res = await asyncio.to_thread(
            self.client.transcribe_file,
            file_path=file_path,
            language=language,
            translation_language="vi-VN",
            use_translation=False,
            wait=True
        )
        
        subtitles = self.client.extract_subtitles(res)
        
        if response_format == "srt":
            return self._to_srt(subtitles)
        elif response_format == "vtt":
            return self._to_vtt(subtitles)
        elif response_format == "text":
            return subtitles.full_text
        else: # default json or verbose_json
            return json.dumps({"text": subtitles.full_text}, ensure_ascii=False)
