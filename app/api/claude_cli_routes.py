import logging
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.key_manager import _get_master_keys, list_keys
from app.core.model_manager import get_available_models
from app.core.security import get_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claude-cli", tags=["claude-cli"])

INSTALL_GUIDE = {
    "powershell": "irm https://storage.googleapis.com/claude-code-dist/install.ps1 | iex",
    "npm": "npm install -g @anthropic-ai/claude-code",
    "bash": "curl -fsSL https://claude.ai/install.sh | bash",
    "docs_url": "https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview",
}


def find_claude_binary() -> Optional[str]:
    """Find installed claude executable in PATH or standard user directories."""
    # 1. Standard PATH resolution
    found = shutil.which("claude")
    if found:
        return os.path.abspath(found)

    # 2. Check platform-specific common installation paths
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".local", "bin", "claude.exe"),
        os.path.join(home, ".local", "bin", "claude"),
        os.path.join(home, "bin", "claude.exe"),
        os.path.join(home, "bin", "claude"),
        os.path.expandvars(r"%APPDATA%\npm\claude.cmd"),
        os.path.expandvars(r"%APPDATA%\npm\claude"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Claude\claude.exe"),
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
        os.path.join(home, ".npm-global", "bin", "claude"),
    ]

    for p in candidates:
        if p and os.path.isfile(p):
            return os.path.abspath(p)

    return None


def get_user_bin_dir() -> str:
    """Returns path to ~/bin directory."""
    return os.path.abspath(os.path.expanduser("~/bin"))


def get_gclaude_bat_path() -> str:
    return os.path.join(get_user_bin_dir(), "gclaude.bat")


def get_gclaude_sh_path() -> str:
    return os.path.join(get_user_bin_dir(), "gclaude")


def read_current_gclaude_model() -> str:
    bat_path = get_gclaude_bat_path()
    if os.path.exists(bat_path):
        try:
            with open(bat_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            m = re.search(r"--model\s+([^\s%]+)", content)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
    return "max-gem"


@router.get("/status", summary="Check Claude CLI installation status and gclaude.bat setup")
async def get_claude_cli_status(api_key: str = Depends(get_api_key)) -> Dict[str, Any]:
    claude_bin = find_claude_binary()
    bat_path = get_gclaude_bat_path()
    sh_path = get_gclaude_sh_path()

    return {
        "installed": bool(claude_bin),
        "claude_path": claude_bin,
        "bin_dir": get_user_bin_dir(),
        "gclaude_bat_path": bat_path,
        "gclaude_sh_path": sh_path,
        "gclaude_exists": os.path.exists(bat_path) or os.path.exists(sh_path),
        "current_model": read_current_gclaude_model(),
        "default_model": "max-gem",
        "install_guide": INSTALL_GUIDE,
        "available_models": await get_available_models(),
    }


class ClaudeCliSetupRequest(BaseModel):
    model: str = "max-gem"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    launch: bool = False


@router.post("/setup", summary="Generate/update gclaude.bat in ~/bin with configured model")
async def setup_claude_cli(
    req: ClaudeCliSetupRequest,
    api_key: str = Depends(get_api_key),
) -> Dict[str, Any]:
    target_model = req.model.strip() or "max-gem"

    # Resolve token to use in gclaude.bat:
    # 1. Explicitly provided
    # 2. Key used to authenticate this request
    # 3. Master key from environment
    # 4. First active key in database
    resolved_key = (req.api_key or "").strip()
    if not resolved_key:
        resolved_key = api_key.strip()
    if not resolved_key:
        master_keys = list(_get_master_keys())
        if master_keys:
            resolved_key = master_keys[0]
    if not resolved_key:
        active_keys = [k for k in list_keys() if k.get("is_active")]
        if active_keys:
            resolved_key = active_keys[0]["key"]

    port = os.environ.get("AGY_PORT", "26767")
    base_url = (req.base_url or "").strip() or f"http://127.0.0.1:{port}/anthropic"

    bin_dir = get_user_bin_dir()
    os.makedirs(bin_dir, exist_ok=True)

    bat_path = get_gclaude_bat_path()
    sh_path = get_gclaude_sh_path()

    # Backup existing files before overwriting
    if os.path.exists(bat_path):
        try:
            shutil.copyfile(bat_path, f"{bat_path}.bak")
        except Exception as exc:
            logger.warning(f"[claude-cli] Failed to backup {bat_path}: {exc}")

    if os.path.exists(sh_path):
        try:
            shutil.copyfile(sh_path, f"{sh_path}.bak")
        except Exception as exc:
            logger.warning(f"[claude-cli] Failed to backup {sh_path}: {exc}")

    bat_content = f"""@echo off
set "ANTHROPIC_BASE_URL={base_url}"
set "ANTHROPIC_AUTH_TOKEN={resolved_key}"
set "ANTHROPIC_MODEL={target_model}"
set "ANTHROPIC_DEFAULT_OPUS_MODEL={target_model}"
set "ANTHROPIC_DEFAULT_SONNET_MODEL={target_model}"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL={target_model}"
set "ANTHROPIC_DEFAULT_FABLE_MODEL={target_model}"
set "CLAUDE_CODE_SUBAGENT_MODEL={target_model}"
set "CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000"
set "CLAUDE_CODE_EFFORT_LEVEL=max"
set "API_TIMEOUT_MS=3000000"
set "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1"
claude --model {target_model} %*
"""

    sh_content = f"""#!/usr/bin/env bash
export ANTHROPIC_BASE_URL="{base_url}"
export ANTHROPIC_AUTH_TOKEN="{resolved_key}"
export ANTHROPIC_MODEL="{target_model}"
export ANTHROPIC_DEFAULT_OPUS_MODEL="{target_model}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="{target_model}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="{target_model}"
export ANTHROPIC_DEFAULT_FABLE_MODEL="{target_model}"
export CLAUDE_CODE_SUBAGENT_MODEL="{target_model}"
export CLAUDE_CODE_AUTO_COMPACT_WINDOW="1000000"
export CLAUDE_CODE_EFFORT_LEVEL="max"
export API_TIMEOUT_MS="3000000"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"
exec claude --model "{target_model}" "$@"
"""

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    with open(sh_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(sh_content)

    try:
        os.chmod(sh_path, 0o755)
    except Exception:
        pass

    # Also update gclaude-settings.json if it exists in bin_dir
    settings_json_path = os.path.join(bin_dir, "gclaude-settings.json")
    if os.path.exists(settings_json_path):
        try:
            import json

            with open(settings_json_path, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
            env_map = settings_data.setdefault("env", {})
            env_map["ANTHROPIC_BASE_URL"] = base_url
            env_map["ANTHROPIC_AUTH_TOKEN"] = resolved_key
            env_map["ANTHROPIC_MODEL"] = target_model
            env_map["ANTHROPIC_DEFAULT_OPUS_MODEL"] = target_model
            env_map["ANTHROPIC_DEFAULT_SONNET_MODEL"] = target_model
            env_map["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = target_model
            env_map["ANTHROPIC_DEFAULT_FABLE_MODEL"] = target_model
            env_map["CLAUDE_CODE_SUBAGENT_MODEL"] = target_model
            env_map["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = "1000000"
            env_map["CLAUDE_CODE_EFFORT_LEVEL"] = "max"
            env_map["API_TIMEOUT_MS"] = "3000000"
            env_map["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
            settings_data["model"] = target_model
            with open(settings_json_path, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.warning(f"[claude-cli] Failed to update {settings_json_path}: {exc}")

    logger.info(f"[claude-cli] Configured gclaude.bat and gclaude in {bin_dir} with model={target_model}")

    launched = False
    if req.launch:
        try:
            if sys.platform == "win32":
                subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", "gclaude"], shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Terminal", sh_path])
            else:
                subprocess.Popen(["x-terminal-emulator", "-e", sh_path])
            launched = True
        except Exception as exc:
            logger.warning(f"[claude-cli] Failed to launch gclaude terminal: {exc}")

    return {
        "status": "ok",
        "bat_path": bat_path,
        "sh_path": sh_path,
        "model": target_model,
        "base_url": base_url,
        "launched": launched,
    }
