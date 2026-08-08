"""
VOD Media Uploader for CapCut STT workflow.
"""

import time
from pathlib import Path
from typing import Any, Dict, Tuple, Union
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    requests = None

from app.capcut_tts_api.config import BASE_URL
from app.capcut_tts_api.exceptions import CapCutAPIError, CapCutUploadError
from app.capcut_tts_api.models import DeviceConfig, UploadResult
from app.capcut_tts_api.signer import (
    aws4_authorization,
    compact_json,
    common_query,
    base_headers,
    crc32_hex,
    file_md5,
    make_sign_header,
    utc_now_for_vod,
)


def _checked_json_response(resp: Any, label: str) -> Dict[str, Any]:
    try:
        data = resp.json()
    except Exception as exc:
        raise CapCutAPIError(
            f"{label} returned non-JSON HTTP {resp.status_code}: {resp.text[:500]}",
            status_code=resp.status_code,
        ) from exc
    if resp.status_code >= 400:
        raise CapCutAPIError(f"{label} HTTP {resp.status_code}: {data}", status_code=resp.status_code, response_data=data)
    return data


class VODUploader:
    """
    Handles chunked media upload to CapCut VOD space using AWS SigV4 authorization.
    """

    def __init__(self, device: DeviceConfig, session: Any = None):
        self.device = device
        self.session = session or (requests.Session() if requests else None)

    def _vod_signed_headers(
        self, method: str, url: str, body: bytes, creds: Dict[str, Any]
    ) -> Dict[str, str]:
        amz_date, http_date = utc_now_for_vod()
        device_dict = self.device.to_dict()
        return {
            "Authorization": aws4_authorization(
                method,
                url,
                body,
                creds["access_key_id"],
                creds["secret_access_key"],
                creds["session_token"],
                amz_date,
            ),
            "Date": http_date,
            "User-Agent": f"BDFileUpload({int(time.time() * 1000)})",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": "31536000",
            "X-Amz-Security-Token": creds["session_token"],
            "accept-encoding": "identity",
            "store-country-code": device_dict["loc"].lower(),
            "store-country-code-src": "did",
            "is-dispatch-us-ttp": "0",
            "is-app-region-us-ttp": "0",
            "tdid": device_dict["tdid"],
            "pf": device_dict["pf"],
        }

    def _upload_binary_headers(self, auth: str, crc32: str) -> Dict[str, str]:
        device_dict = self.device.to_dict()
        headers = {
            "Authorization": auth,
            "Date": utc_now_for_vod()[1],
            "User-Agent": f"BDFileUpload({int(time.time() * 1000)})",
            "accept-encoding": "identity",
            "store-country-code": device_dict["loc"].lower(),
            "store-country-code-src": "did",
            "is-dispatch-us-ttp": "0",
            "is-app-region-us-ttp": "0",
            "tdid": device_dict["tdid"],
            "pf": device_dict["pf"],
        }
        if crc32:
            headers["X-Upload-Content-CRC32"] = crc32
        return headers

    def _upload_sign_request(self) -> Tuple[str, Dict[str, str], str]:
        device_dict = self.device.to_dict()
        body = {"biz": "cc_pc_text_recognize", "key_version": "v5"}
        body_text = compact_json(body)
        path = "/lv/v1/upload_sign"
        query = common_query(device_dict, None, include_region=False)
        url = BASE_URL + path + "?" + urlencode(query)
        headers = base_headers(device_dict, body_text, appid=True)
        lower_headers = {k.lower(): v for k, v in headers.items()}
        if "sign" not in lower_headers:
            headers["sign"] = make_sign_header(
                url, device_dict["appvr"], lower_headers["device-time"], device_dict["tdid"]
            )
        return url, headers, body_text

    def upload_file(self, file_path: Union[str, Path]) -> UploadResult:
        """
        Upload audio or video file to CapCut VOD space.

        :param file_path: Path to the media file (.mp3, .m4a, .mp4, etc.)
        :return: UploadResult containing vid, md5, duration_ms, and storage details.
        """
        if requests is None:
            raise CapCutUploadError("The 'requests' package is required for media upload. Run 'pip install requests'.")

        path_obj = Path(file_path)
        if not path_obj.exists():
            raise CapCutUploadError(f"File not found: {file_path}")

        path_str = str(path_obj)
        local_md5 = file_md5(path_str)
        with open(path_str, "rb") as fp:
            data = fp.read()
        part_crc32 = crc32_hex(data)

        # 1. Upload Sign
        url, headers, body_text = self._upload_sign_request()
        sign_resp = self.session.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=60)
        sign_data = _checked_json_response(sign_resp, "upload_sign")
        creds = sign_data.get("data") or {}
        for key in ("domain", "access_key_id", "secret_access_key", "session_token", "space_name"):
            if not creds.get(key):
                raise CapCutUploadError(f"upload_sign missing required field '{key}': {sign_data}")

        # 2. Apply Upload Inner
        apply_url = f"https://{creds['domain']}/top/v1?" + urlencode(
            {
                "Action": "ApplyUploadInner",
                "SpaceName": creds["space_name"],
                "UseQuic": "false",
                "Version": "2020-11-19",
                "device_platform": "win",
            }
        )
        apply_resp = self.session.get(
            apply_url, headers=self._vod_signed_headers("GET", apply_url, b"", creds), timeout=60
        )
        apply_data = _checked_json_response(apply_resp, "ApplyUploadInner")
        node = apply_data["Result"]["InnerUploadAddress"]["UploadNodes"][0]
        store = node["StoreInfos"][0]
        upload_host = node["UploadHost"]
        store_uri = store["StoreUri"]
        upload_id = store["UploadID"]
        upload_auth = store["Auth"]
        vid = node.get("Vid") or (node.get("Vids") or [None])[0]

        # 3. Transfer binary
        transfer_url = f"https://{upload_host}/upload/v1/{store_uri}?" + urlencode(
            {"uploadid": upload_id, "part_number": "0", "phase": "transfer"}
        )
        transfer_resp = self.session.post(
            transfer_url, headers=self._upload_binary_headers(upload_auth, part_crc32), data=data, timeout=300
        )
        _checked_json_response(transfer_resp, "upload transfer")

        # 4. Finish upload
        finish_url = f"https://{upload_host}/upload/v1/{store_uri}?" + urlencode(
            {"uploadmode": "part", "phase": "finish", "uploadid": upload_id}
        )
        finish_body = f"0:{part_crc32}"
        finish_resp = self.session.post(
            finish_url, headers=self._upload_binary_headers(upload_auth, ""), data=finish_body.encode("utf-8"), timeout=60
        )
        _checked_json_response(finish_resp, "upload finish")

        # 5. Commit Upload Inner
        commit_url = f"https://{creds['domain']}/top/v1?" + urlencode(
            {
                "Action": "CommitUploadInner",
                "SpaceName": creds["space_name"],
                "Version": "2020-11-19",
                "device_platform": "win",
            }
        )
        commit_body = compact_json(
            {"Functions": [{"Input": {"SnapshotTime": 0.0}, "Name": "Snapshot"}], "SessionKey": node["SessionKey"]}
        )
        commit_resp = self.session.post(
            commit_url,
            headers=self._vod_signed_headers("POST", commit_url, commit_body.encode("utf-8"), creds),
            data=commit_body.encode("utf-8"),
            timeout=120,
        )
        commit_data = _checked_json_response(commit_resp, "CommitUploadInner")
        result = commit_data["Result"]["Results"][0]
        meta = result.get("VideoMeta") or {}
        duration_ms = int(float(meta.get("Duration") or 0) * 1000) if meta.get("Duration") is not None else 0

        return UploadResult(
            vid=result.get("Vid") or vid,
            md5=meta.get("Md5") or local_md5,
            local_md5=local_md5,
            duration_ms=duration_ms,
            format=meta.get("Format"),
            size=meta.get("Size") or len(data),
            file_type=meta.get("FileType"),
            store_uri=meta.get("Uri") or store_uri,
        )
