"""
Data models and dataclasses for CapCut TTS API client.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
import json
from pathlib import Path
from copy import deepcopy

from app.capcut_tts_api.config import DEFAULT_DEVICE


@dataclass
class DeviceConfig:
    """
    Device profile and identity configuration for CapCut request signing.
    """

    aid: str = DEFAULT_DEVICE["aid"]
    app_name: str = DEFAULT_DEVICE["app_name"]
    appvr: str = DEFAULT_DEVICE["appvr"]
    version_name: str = DEFAULT_DEVICE["version_name"]
    version_code: str = DEFAULT_DEVICE["version_code"]
    channel: str = DEFAULT_DEVICE["channel"]
    device_platform: str = DEFAULT_DEVICE["device_platform"]
    device_type: str = DEFAULT_DEVICE["device_type"]
    device_brand: str = DEFAULT_DEVICE["device_brand"]
    os_version: str = DEFAULT_DEVICE["os_version"]
    device_id: str = DEFAULT_DEVICE["device_id"]
    iid: str = DEFAULT_DEVICE["iid"]
    region: str = DEFAULT_DEVICE["region"]
    loc: str = DEFAULT_DEVICE["loc"]
    lan: str = DEFAULT_DEVICE["lan"]
    pf: str = DEFAULT_DEVICE["pf"]
    tdid: str = DEFAULT_DEVICE["tdid"]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceConfig":
        """Create a DeviceConfig instance from a dictionary, using default values for missing keys."""
        merged = deepcopy(DEFAULT_DEVICE)
        merged.update(data)
        return cls(**{k: v for k, v in merged.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json_file(cls, path: Union[str, Path]) -> "DeviceConfig":
        """Load device config from a JSON file."""
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, str]:
        """Convert device config to dictionary representation."""
        return asdict(self)


@dataclass
class UploadResult:
    """
    Result metadata of a media upload to CapCut VOD space.
    """

    vid: str
    md5: str
    local_md5: str
    duration_ms: int
    format: Optional[str] = None
    size: int = 0
    file_type: Optional[str] = None
    store_uri: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Word:
    """Word-level timing information for STT subtitles."""

    text: str
    start_time: int
    end_time: int
    blank_duration: int = 0


@dataclass
class Utterance:
    """Subtitle sentence block timing and text."""

    text: str
    start_time: int
    end_time: int
    words: List[Word] = field(default_factory=list)


@dataclass
class SubtitleResult:
    """Parsed STT transcription result containing utterances."""

    utterances: List[Utterance] = field(default_factory=list)
    full_text: str = ""

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "SubtitleResult":
        """Parse subtitle payload dictionary into SubtitleResult object."""
        raw_utterances = payload.get("utterances") or []
        utterance_list = []
        text_parts = []

        for item in raw_utterances:
            words = [
                Word(
                    text=w.get("text", ""),
                    start_time=w.get("start_time", 0),
                    end_time=w.get("end_time", 0),
                    blank_duration=w.get("blank_duration", 0),
                )
                for w in item.get("words", [])
            ]
            text = item.get("text", "")
            if text:
                text_parts.append(text)
            utterance_list.append(
                Utterance(
                    text=text,
                    start_time=item.get("start_time", 0),
                    end_time=item.get("end_time", 0),
                    words=words,
                )
            )
        return cls(utterances=utterance_list, full_text=" ".join(text_parts))


@dataclass
class VoiceInfo:
    """Voice metadata object representing available CapCut TTS voices."""

    voice_type: str
    display_name: str
    resource_id: str
    lang: str
    lan: str
    captured_at: Optional[str] = None

    @classmethod
    def load_catalog(cls, file_path: Union[str, Path]) -> List["VoiceInfo"]:
        """Load list of voices from Voice.json catalog file."""
        path = Path(file_path)
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return [cls(**item) for item in data]
