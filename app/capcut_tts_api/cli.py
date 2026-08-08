"""
Command Line Interface for CapCut TTS API client.
"""

import argparse
import json
import sys
from pathlib import Path

from app.capcut_tts_api.client import CapCutClient
from app.capcut_tts_api.models import DeviceConfig


def save_json(obj: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(obj, fp, ensure_ascii=False, indent=2)
        fp.write("\n")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="capcut-tts-api",
        description="Build/call CapCut common_task TTS/STT requests",
    )
    ap.add_argument(
        "mode",
        choices=[
            "upload-audio",
            "tts-new",
            "tts-query",
            "stt-new",
            "stt-query",
            "stt-file",
            "list-voices",
        ],
        help="Action mode to execute",
    )
    ap.add_argument("--device-json", help="Override device/query values from a JSON file")
    ap.add_argument("--dry-run", action="store_true", help="Print request details without making HTTP call")
    ap.add_argument("--out", help="Write output response JSON to file")

    ap.add_argument("--text", action="append", help="TTS text segment; repeatable")
    ap.add_argument("--text-file", help="TTS text file, one segment per line")
    ap.add_argument("--voice", default="BV074_streaming", help="TTS voice character name or display name")
    ap.add_argument("--resource-id", default=None, help="TTS voice resource ID (automatically resolved if omitted)")
    ap.add_argument("--rate", default="1.0", help="TTS speech rate multiplier")

    ap.add_argument("--audio-vid", help="STT uploaded audio/video vid")
    ap.add_argument("--audio-md5", help="STT source audio md5 from app/upload flow")
    ap.add_argument("--audio-file", help="MP3/M4A/MP4 audio/video file to upload before STT")
    ap.add_argument("--duration-ms", type=int, help="Audio duration in milliseconds")
    ap.add_argument("--language", default="zh-CN", help="STT source audio language code")
    ap.add_argument("--translation-language", default="vi-VN", help="STT target translation language code")
    ap.add_argument("--use-translation", action="store_true", help="Enable STT translation")

    ap.add_argument("--task-id", help="Task ID for query mode")
    ap.add_argument("--token", help="Task token for query mode")
    ap.add_argument("--bind-id", default="", help="Task bind ID")
    return ap


def main(args_list=None) -> None:
    ap = build_parser()
    args = ap.parse_args(args_list)

    # Device configuration loading
    device = DeviceConfig()
    if args.device_json:
        device = DeviceConfig.from_json_file(args.device_json)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    client = CapCutClient(device=device)

    # 1. List voices
    if args.mode == "list-voices":
        voices = client.list_voices(lang=args.language if args.language != "zh-CN" else None)
        voice_dicts = [
            {
                "display_name": v.display_name,
                "voice_type": v.voice_type,
                "resource_id": v.resource_id,
                "lang": v.lang,
            }
            for v in voices
        ]
        out_data = {"voices": voice_dicts}
        print(json.dumps(out_data, ensure_ascii=False, indent=2))
        if args.out:
            save_json(out_data, args.out)
        return

    # 2. Upload Audio & STT File combined mode
    if args.mode in {"upload-audio", "stt-file"}:
        if not args.audio_file:
            print("Error: --audio-file is required for mode upload-audio / stt-file", file=sys.stderr)
            sys.exit(1)
        upload_info = client.upload_audio(args.audio_file)
        upload_dict = upload_info.to_dict()

        if args.mode == "upload-audio":
            if args.out:
                save_json(upload_dict, args.out)
            print(json.dumps(upload_dict, ensure_ascii=False, indent=2))
            return

        # stt-file flow continues to stt-new
        args.audio_vid = upload_info.vid
        args.audio_md5 = upload_info.md5
        if not args.duration_ms and upload_info.duration_ms:
            args.duration_ms = upload_info.duration_ms
        args.mode = "stt-new"
        print("Upload complete:")
        print(json.dumps(upload_dict, ensure_ascii=False, indent=2))

    # 3. Dry-run or Execute API requests
    url, headers, body_text = None, None, None

    if args.mode == "tts-new":
        texts = args.text or []
        if args.text_file:
            with open(args.text_file, "r", encoding="utf-8") as fp:
                texts.extend([line.strip() for line in fp if line.strip()])
        if not texts:
            print("Error: need --text or --text-file", file=sys.stderr)
            sys.exit(1)
        url, headers, body_text = client.build_tts_new_request(
            texts, args.voice, args.resource_id, args.rate
        )

    elif args.mode == "stt-new":
        if not args.audio_vid or not args.audio_md5:
            print("Error: need --audio-vid and --audio-md5", file=sys.stderr)
            sys.exit(1)
        url, headers, body_text = client.build_stt_new_request(
            args.audio_vid,
            args.audio_md5,
            args.duration_ms or 10000,
            args.language,
            args.translation_language,
            args.use_translation,
        )

    elif args.mode in {"tts-query", "stt-query"}:
        if not args.task_id or not args.token:
            print("Error: need --task-id and --token", file=sys.stderr)
            sys.exit(1)
        url, headers, body_text = client.build_query_request(
            args.task_id, args.token, mode=args.mode, bind_id=args.bind_id
        )
    else:
        print(f"Error: unknown mode {args.mode}", file=sys.stderr)
        sys.exit(1)

    req_dump = {"url": url, "headers": headers, "body": json.loads(body_text)}

    if args.dry_run:
        print(json.dumps(req_dump, ensure_ascii=False, indent=2))
        return

    if client.session is None:
        print("Error: pip install requests is required to execute API requests", file=sys.stderr)
        sys.exit(1)

    resp = client.session.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=60)
    print(resp.status_code)
    print(resp.text)
    if args.out:
        try:
            save_json(resp.json(), args.out)
        except Exception:
            with open(args.out, "w", encoding="utf-8") as fp:
                fp.write(resp.text)


if __name__ == "__main__":
    main()
