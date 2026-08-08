"""
High-level Python API Client for CapCut Text-to-Speech (TTS) and Speech-to-Text (STT) tasks.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    requests = None

from app.capcut_tts_api.config import BASE_URL
from app.capcut_tts_api.exceptions import CapCutAPIError, CapCutError, CapCutTaskError
from app.capcut_tts_api.models import DeviceConfig, SubtitleResult, UploadResult, VoiceInfo
from app.capcut_tts_api.signer import (
    base_headers,
    compact_json,
    common_query,
    escape_xml,
    make_sign_header,
    make_tts_payload_sign,
)
from app.capcut_tts_api.uploader import VODUploader


def _checked_json_response(resp: Any, label: str) -> Dict[str, Any]:
    try:
        data = resp.json()
    except Exception as exc:
        raise CapCutAPIError(
            f"{label} returned non-JSON HTTP {resp.status_code}: {resp.text[:500]}",
            status_code=resp.status_code,
        ) from exc
    if resp.status_code >= 400:
        raise CapCutAPIError(
            f"{label} HTTP {resp.status_code}: {data}",
            status_code=resp.status_code,
            response_data=data,
        )
    return data


class CapCutClient:
    """
    Main CapCut API client for generating TTS and transcribing STT audio/video files.
    """

    def __init__(
        self,
        device: Optional[Union[DeviceConfig, Dict[str, Any], str, Path]] = None,
        session: Optional[Any] = None,
    ):
        """
        Initialize CapCutClient.

        :param device: Device configuration instance, dictionary, or path to device.json file.
        :param session: Optional requests.Session instance for connection pooling.
        """
        if isinstance(device, DeviceConfig):
            self.device = device
        elif isinstance(device, (str, Path)):
            self.device = DeviceConfig.from_json_file(device)
        elif isinstance(device, dict):
            self.device = DeviceConfig.from_dict(device)
        else:
            self.device = DeviceConfig()

        self.session = session or (requests.Session() if requests else None)

    # -------------------------------------------------------------------------
    # Voice Resolution Helper
    # -------------------------------------------------------------------------

    def resolve_voice(
        self,
        voice: Optional[str] = None,
        resource_id: Optional[str] = None,
        catalog_path: Optional[Union[str, Path]] = None,
    ) -> Tuple[str, str]:
        """
        Resolve voice_type and resource_id from Voice.json catalog or explicit inputs.

        :param voice: Voice type string (e.g. 'BV421_vivn_streaming', 'BV074_streaming') or display name
        :param resource_id: Optional explicit voice resource ID string
        :return: Tuple of (voice_type, resource_id)
        """
        default_voice = "BV074_streaming"
        default_resource_id = "7102355709945188865"

        target_voice = voice or default_voice
        target_res = resource_id

        # Try lookup in Voice.json catalog
        all_voices = self.list_voices(catalog_path=catalog_path)
        target_lower = target_voice.lower().strip() if target_voice else ""

        # 1. Primary match: voice_type
        for v in all_voices:
            if v.voice_type.lower() == target_lower:
                return v.voice_type, target_res or v.resource_id

        # 2. Secondary match: display_name or resource_id
        for v in all_voices:
            if v.display_name.lower() == target_lower or (target_res and v.resource_id == target_res):
                return v.voice_type, target_res or v.resource_id

        # Fallback to provided values or defaults
        resolved_voice = target_voice
        resolved_res = target_res or default_resource_id
        return resolved_voice, resolved_res

    # -------------------------------------------------------------------------
    # Request Payload Builders (Dry-run capable)
    # -------------------------------------------------------------------------

    def build_tts_new_request(
        self,
        texts: Union[str, List[str]],
        voice: Optional[str] = "BV074_streaming",
        resource_id: Optional[str] = None,
        rate: str = "1.0",
    ) -> Tuple[str, Dict[str, str], str]:
        """
        Build URL, headers, and body string for creating a new TTS task.
        Automatically resolves resource_id for voice character if omitted.
        """
        if isinstance(texts, str):
            text_list = [texts]
        else:
            text_list = list(texts)

        if not text_list:
            raise ValueError("texts must contain at least one string")

        voice_type, final_resource_id = self.resolve_voice(voice=voice, resource_id=resource_id)

        device_dict = self.device.to_dict()
        babi = {
            "feature_entrance": "editor",
            "feature_entrance_detail": "editor-feature-text_to_speech",
            "feature_key": "text_to_speech",
            "scenario": "video_editor",
        }
        voice_blocks = []
        for text in text_list:
            voice_blocks.append(
                f'    <voice name="{voice_type}" mock_tone_info="" platform="sami" '
                f'resource_id="{final_resource_id}" emotion="" emotion_scale="0" style="" role="" '
                f'moyin_emotion="" is_clone_tone="false" need_subtitle_timestamp="false">\n'
                f'        <prosody rate="{rate}">{escape_xml(text)}</prosody>\n'
                f'    </voice>'
            )
        ssml = (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">\n'
            + "\n".join(voice_blocks)
            + "\n</speak>"
        )
        extra_info = compact_json({"benefit_info": {}})
        payload = {
            "audio_format": "mp3",
            "babi_param": compact_json(babi),
            "credit_disable": False,
            "extra_info": extra_info,
            "need_merge_voice": False,
            "need_subtitle_timestamp": False,
            "scene": "text_to_speech",
            "ssml": ssml,
        }
        payload["sign"] = make_tts_payload_sign(
            ssml, extra_info, device_dict["device_id"], device_dict["aid"]
        )
        body = {
            "bind_id": str(uuid.uuid4()),
            "can_queue": True,
            "enter_from": "text_to_speech",
            "tasks": [
                {
                    "context": str(uuid.uuid4()),
                    "payload": compact_json(payload),
                    "req_key": "sami_text_to_speech",
                    "task_version": "v3",
                }
            ],
        }

        body_text = compact_json(body)
        path = "/lv/v1/common_task/new"
        query = common_query(device_dict, babi, include_region=True)
        url = BASE_URL + path + "?" + urlencode(query)
        headers = base_headers(device_dict, body_text, appid=True)
        lower_headers = {k.lower(): v for k, v in headers.items()}
        if "sign" not in lower_headers:
            headers["sign"] = make_sign_header(
                url, device_dict["appvr"], lower_headers["device-time"], device_dict["tdid"]
            )
        return url, headers, body_text

    def build_stt_new_request(
        self,
        audio_vid: str,
        audio_md5: str,
        duration_ms: int = 10000,
        language: str = "zh-CN",
        translation_language: str = "vi-VN",
        use_translation: bool = False,
    ) -> Tuple[str, Dict[str, str], str]:
        """
        Build URL, headers, and body string for creating a new STT task.
        """
        device_dict = self.device.to_dict()
        babi = {
            "feature_entrance": "editor",
            "feature_entrance_detail": "editor-elements-captions-subtitle_recognition",
            "feature_key": "subtitle_recognition",
            "scenario": "video_editor",
        }
        cap_json = {
            "adjust_endtime": 200,
            "audio": audio_vid,
            "audio_type": "vid",
            "caption_type": 0,
            "client_request_id": str(uuid.uuid4()),
            "duration": int(duration_ms),
            "enable_cache": True,
            "enter_from": "asr",
            "language": language,
            "max_lines": 1,
            "md5": audio_md5,
            "pack_options": {"need_attribute": True},
            "songs_info": [
                {"end_time": float(duration_ms) - 10.334, "id": "", "start_time": 0}
            ],
            "translation_language": translation_language,
            "use_translation": bool(use_translation),
            "words_per_line": 15,
        }
        body = {
            "bind_id": str(uuid.uuid4()).upper(),
            "can_queue": True,
            "enter_from": "asr",
            "tasks": [
                {
                    "context": str(uuid.uuid4()),
                    "payload": compact_json({"cap_json": cap_json}),
                    "req_key": "cc_audio_subtitle_asr",
                    "task_version": "v3",
                }
            ],
        }

        body_text = compact_json(body)
        path = "/lv/v1/common_task/new"
        query = common_query(device_dict, babi, include_region=True)
        url = BASE_URL + path + "?" + urlencode(query)
        headers = base_headers(device_dict, body_text, appid=False)
        lower_headers = {k.lower(): v for k, v in headers.items()}
        if "sign" not in lower_headers:
            headers["sign"] = make_sign_header(
                url, device_dict["appvr"], lower_headers["device-time"], device_dict["tdid"]
            )
        return url, headers, body_text

    def build_query_request(
        self,
        task_id: str,
        token: str,
        mode: str = "tts",
        bind_id: str = "",
    ) -> Tuple[str, Dict[str, str], str]:
        """
        Build URL, headers, and body string for querying a task.
        :param mode: "tts" or "stt"
        """
        req_key = (
            "sami_text_to_speech"
            if mode in ("tts", "tts-query")
            else "cc_audio_subtitle_asr"
        )
        device_dict = self.device.to_dict()
        body = {
            "tasks": [
                {
                    "bind_id": bind_id,
                    "id": task_id,
                    "req_key": req_key,
                    "task_version": "v3",
                    "token": token,
                }
            ]
        }
        body_text = compact_json(body)
        path = "/lv/v1/common_task/query"
        query = common_query(device_dict, None, include_region=False)
        url = BASE_URL + path + "?" + urlencode(query)
        headers = base_headers(
            device_dict, body_text, appid=(mode in ("tts", "tts-query"))
        )
        lower_headers = {k.lower(): v for k, v in headers.items()}
        if "sign" not in lower_headers:
            headers["sign"] = make_sign_header(
                url, device_dict["appvr"], lower_headers["device-time"], device_dict["tdid"]
            )
        return url, headers, body_text

    # -------------------------------------------------------------------------
    # Core API Execution Methods
    # -------------------------------------------------------------------------

    def create_tts_task(
        self,
        texts: Union[str, List[str]],
        voice: Optional[str] = "BV074_streaming",
        resource_id: Optional[str] = None,
        rate: str = "1.0",
    ) -> Dict[str, Any]:
        """
        Submit a new Text-to-Speech task to CapCut API.
        """
        if self.session is None:
            raise CapCutError("The 'requests' package is required. Run 'pip install requests'.")
        url, headers, body_text = self.build_tts_new_request(texts, voice, resource_id, rate)
        resp = self.session.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=60)
        return _checked_json_response(resp, "create_tts_task")

    def query_tts_task(
        self, task_id: str, token: str, bind_id: str = ""
    ) -> Dict[str, Any]:
        """
        Query TTS task status by task_id and token.
        """
        if self.session is None:
            raise CapCutError("The 'requests' package is required. Run 'pip install requests'.")
        url, headers, body_text = self.build_query_request(
            task_id, token, mode="tts", bind_id=bind_id
        )
        resp = self.session.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=60)
        return _checked_json_response(resp, "query_tts_task")

    def generate_speech(
        self,
        texts: Union[str, List[str]],
        voice: Optional[str] = "BV074_streaming",
        resource_id: Optional[str] = None,
        rate: str = "1.0",
        wait: bool = True,
        poll_interval: float = 1.0,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Convenience method: Submits TTS task and polls until completed.
        """
        create_res = self.create_tts_task(texts, voice, resource_id, rate)
        if not wait:
            return create_res

        tasks = (create_res.get("data") or {}).get("tasks") or []
        if not tasks:
            raise CapCutTaskError(f"No task returned from API: {create_res}")

        task_id = tasks[0]["id"]
        token = tasks[0]["token"]

        start_time = time.time()
        while time.time() - start_time < timeout:
            query_res = self.query_tts_task(task_id, token)
            query_tasks = (query_res.get("data") or {}).get("tasks") or []
            if query_tasks:
                status = query_tasks[0].get("status")
                if status in ("success", "succeed"):
                    return query_res
                elif status in ("failed", "fail"):
                    raise CapCutTaskError(f"TTS Task failed: {query_res}")
            time.sleep(poll_interval)

        raise CapCutTaskError(f"TTS Task timed out after {timeout} seconds")

    def upload_audio(self, file_path: Union[str, Path]) -> UploadResult:
        """
        Upload audio or video file to VOD space.
        """
        uploader = VODUploader(self.device, session=self.session)
        return uploader.upload_file(file_path)

    def create_stt_task(
        self,
        audio_vid: str,
        audio_md5: str,
        duration_ms: int = 10000,
        language: str = "zh-CN",
        translation_language: str = "vi-VN",
        use_translation: bool = False,
    ) -> Dict[str, Any]:
        """
        Submit Speech-to-Text task using pre-uploaded media vid and md5.
        """
        if self.session is None:
            raise CapCutError("The 'requests' package is required. Run 'pip install requests'.")
        url, headers, body_text = self.build_stt_new_request(
            audio_vid, audio_md5, duration_ms, language, translation_language, use_translation
        )
        resp = self.session.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=60)
        return _checked_json_response(resp, "create_stt_task")

    def query_stt_task(
        self, task_id: str, token: str, bind_id: str = ""
    ) -> Dict[str, Any]:
        """
        Query STT task status by task_id and token.
        """
        if self.session is None:
            raise CapCutError("The 'requests' package is required. Run 'pip install requests'.")
        url, headers, body_text = self.build_query_request(
            task_id, token, mode="stt", bind_id=bind_id
        )
        resp = self.session.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=60)
        return _checked_json_response(resp, "query_stt_task")

    def transcribe_file(
        self,
        file_path: Union[str, Path],
        language: str = "zh-CN",
        translation_language: str = "vi-VN",
        use_translation: bool = False,
        wait: bool = True,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        """
        Upload media file, create STT task, and optionally poll for completion.
        """
        upload_res = self.upload_audio(file_path)
        duration_ms = upload_res.duration_ms or 10000

        stt_res = self.create_stt_task(
            audio_vid=upload_res.vid,
            audio_md5=upload_res.md5,
            duration_ms=duration_ms,
            language=language,
            translation_language=translation_language,
            use_translation=use_translation,
        )

        if not wait:
            return stt_res

        tasks = (stt_res.get("data") or {}).get("tasks") or []
        if not tasks:
            raise CapCutTaskError(f"No STT task returned from API: {stt_res}")

        task_id = tasks[0]["id"]
        token = tasks[0]["token"]

        start_time = time.time()
        while time.time() - start_time < timeout:
            query_res = self.query_stt_task(task_id, token)
            query_tasks = (query_res.get("data") or {}).get("tasks") or []
            if query_tasks:
                status = query_tasks[0].get("status")
                if status in ("success", "succeed"):
                    return query_res
                elif status in ("failed", "fail"):
                    raise CapCutTaskError(f"STT Task failed: {query_res}")
            time.sleep(poll_interval)

        raise CapCutTaskError(f"STT Task timed out after {timeout} seconds")

    def extract_subtitles(self, query_response: Dict[str, Any]) -> SubtitleResult:
        """
        Extract and parse subtitles from an STT query response payload.
        """
        try:
            tasks = (query_response.get("data") or {}).get("tasks") or []
            if not tasks:
                return SubtitleResult()
            raw_payload = tasks[0].get("payload", "{}")
            if isinstance(raw_payload, str):
                payload_dict = json.loads(raw_payload)
            else:
                payload_dict = raw_payload
            return SubtitleResult.from_payload(payload_dict)
        except Exception as exc:
            raise CapCutError(f"Failed to parse subtitle payload: {exc}") from exc

    def list_voices(
        self, lang: Optional[str] = None, catalog_path: Optional[Union[str, Path]] = None
    ) -> List[VoiceInfo]:
        """
        List available CapCut TTS voices from catalog file.
        """
        path = catalog_path or Path(__file__).parent.parent / "Voice.json"
        voices = VoiceInfo.load_catalog(path)
        if lang:
            return [v for v in voices if v.lang.lower() == lang.lower() or v.lan.lower() == lang.lower()]
        return voices
