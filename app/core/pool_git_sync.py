import asyncio
import os
import subprocess


def _pool_dir() -> str:
    return os.path.expanduser(os.environ.get("AGY_POOL_DIR", "~/.agy2api-pool"))


def _git_sync(*args: str) -> str:
    result = subprocess.run(["git", "-C", _pool_dir(), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


async def git_pull() -> str:
    return await asyncio.to_thread(_git_sync, "pull")


def _git_commit_and_push_sync(message: str) -> str:
    _git_sync("add", "-A")
    result = subprocess.run(["git", "-C", _pool_dir(), "commit", "-m", message], capture_output=True, text=True)
    if result.returncode != 0 and "nothing to commit" not in result.stdout.lower():
        raise RuntimeError(f"git commit failed: {result.stderr.strip()}")
    return _git_sync("push")


async def git_commit_and_push(message: str = "Update account pool") -> str:
    return await asyncio.to_thread(_git_commit_and_push_sync, message)
