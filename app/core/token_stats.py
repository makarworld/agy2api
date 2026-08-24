"""Shared token accounting helpers.

Gemini / Cloud Code Assist reports ``cachedContentTokenCount`` as a subset of
``promptTokenCount`` (already included in input). Cache must not be added on
top of prompt when computing totals.
"""

from typing import Mapping


def clamp_cache_tokens(prompt_tokens: int, cache_tokens: int) -> int:
    prompt_tokens = max(0, int(prompt_tokens or 0))
    cache_tokens = max(0, int(cache_tokens or 0))
    return min(cache_tokens, prompt_tokens)


def request_total_tokens(prompt_tokens: int, completion_tokens: int, cache_tokens: int = 0) -> int:
    """Billable / processed tokens for one request (cache is informational only)."""
    return max(0, int(prompt_tokens or 0)) + max(0, int(completion_tokens or 0))


def uncached_prompt_tokens(prompt_tokens: int, cache_tokens: int) -> int:
    return max(0, int(prompt_tokens or 0) - clamp_cache_tokens(prompt_tokens, cache_tokens))


def summarize_token_fields(row: Mapping[str, int]) -> dict:
    prompt = int(row.get("prompt_tokens") or row.get("total_prompt_tokens") or 0)
    completion = int(row.get("completion_tokens") or row.get("total_completion_tokens") or 0)
    cache = clamp_cache_tokens(prompt, int(row.get("cache_tokens") or row.get("total_cache_tokens") or 0))
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cache_tokens": cache,
        "uncached_prompt_tokens": prompt - cache,
        "total_tokens": request_total_tokens(prompt, completion, cache),
    }
