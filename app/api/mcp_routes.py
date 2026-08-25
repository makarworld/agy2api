import asyncio
import json
import logging
import time
from typing import Any, Optional
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.core import stats_store
from app.core import pool_manager
from app.core import oauth_refresh
from app.core import app_state
from app.core.security import API_KEY, ADMIN_PASSWORD, ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

router = APIRouter()

SERVER_INFO = {
    "name": "agy2api-mcp",
    "version": "1.0.0",
}

AVAILABLE_TOOLS = [
    {
        "name": "get_stats_summary",
        "description": "Get high-level cumulative stats: uptime, total requests, success/failed counts, token usage (IN, OUT, CACHE), and breakdown by models and accounts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_hours": {
                    "type": "integer",
                    "description": "Optional time window in hours (e.g. 24 for last 24h, omit for all time)",
                }
            },
        },
    },
    {
        "name": "get_recent_errors",
        "description": "Get detailed list of recent failed requests with full diagnostic info (error type, error message/preview, prompt preview, latency, model, pool account, timestamp).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of error requests to return (default 20, max 100)",
                    "default": 20,
                },
                "window_hours": {
                    "type": "integer",
                    "description": "Optional time window in hours (e.g. 24 for last 24 hours)",
                },
                "model": {
                    "type": "string",
                    "description": "Optional filter by model name",
                },
            },
        },
    },
    {
        "name": "get_requests",
        "description": "List requests with comprehensive filtering and pagination (success or failed, model, search query, chat_id).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max items to return (default 20, max 100)",
                    "default": 20,
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset",
                    "default": 0,
                },
                "status": {
                    "type": "string",
                    "enum": ["all", "success", "failed"],
                    "description": "Filter by request status (all, success, failed)",
                    "default": "all",
                },
                "model": {
                    "type": "string",
                    "description": "Filter by model name",
                },
                "search": {
                    "type": "string",
                    "description": "Search term in prompt, response, chat_id, or error",
                },
                "window_hours": {
                    "type": "integer",
                    "description": "Filter by past N hours",
                },
            },
        },
    },
    {
        "name": "get_pool_accounts_and_limits",
        "description": "Get all accounts in the pool with health status, proxy, usage metrics, and current Gemini (5h, 7d) and Claude (5h, 7d) quota limits and reset times.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _check_mcp_auth(request: Request) -> None:
    """Verify auth key from Authorization header, x-api-key header, or query param."""
    auth_header = request.headers.get("Authorization")
    x_api_key = request.headers.get("x-api-key")
    query_key = request.query_params.get("api_key") or request.query_params.get("key")

    token = None
    if auth_header:
        parts = auth_header.split(" ", 1)
        token = parts[1] if len(parts) == 2 else auth_header
    elif x_api_key:
        token = x_api_key
    elif query_key:
        token = query_key

    valid_keys = {k for k in [API_KEY, ADMIN_PASSWORD, ANTHROPIC_API_KEY] if k}
    if not token or token not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key for MCP endpoint",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _handle_tool_call(name: str, arguments: dict) -> Any:
    if name == "get_stats_summary":
        window_hours = arguments.get("window_hours")
        window_seconds = int(window_hours) * 3600 if window_hours else None
        summary = await stats_store.get_summary(window_seconds)
        summary["uptime_seconds"] = int(time.time() - app_state.START_TIME)
        summary["app_start_ts"] = app_state.START_TIME
        return summary

    elif name == "get_recent_errors":
        limit = min(max(1, int(arguments.get("limit", 20))), 100)
        window_hours = arguments.get("window_hours")
        window_seconds = int(window_hours) * 3600 if window_hours else None
        model = arguments.get("model")

        data = await stats_store.get_requests_list(
            limit=limit,
            offset=0,
            status="failed",
            model=model,
            window_seconds=window_seconds,
        )
        return {
            "total_errors_in_window": data.get("total", 0),
            "errors": data.get("requests", []),
        }

    elif name == "get_requests":
        limit = min(max(1, int(arguments.get("limit", 20))), 100)
        offset = max(0, int(arguments.get("offset", 0)))
        req_status = arguments.get("status", "all")
        model = arguments.get("model")
        search = arguments.get("search")
        window_hours = arguments.get("window_hours")
        window_seconds = int(window_hours) * 3600 if window_hours else None

        data = await stats_store.get_requests_list(
            limit=limit,
            offset=offset,
            status=req_status if req_status in ("success", "failed") else None,
            model=model,
            search=search,
            window_seconds=window_seconds,
        )
        return data

    elif name == "get_pool_accounts_and_limits":
        accounts = pool_manager.list_accounts()
        states = {s["account_id"]: s for s in await stats_store.list_pool_account_states()}
        active_id = pool_manager.get_active_account_id()

        account_items = (
            accounts if pool_manager.pool_enabled() else (accounts or [{"id": "active", "label": "Default Session"}])
        )
        res_accounts = []
        for acc in account_items:
            acc_id = acc.get("id", "active")
            state = states.get(acc_id, {})
            token, proxy, account_dir = pool_manager.get_account_token_and_proxy(acc_id)
            quota_data = {}
            if token or account_dir:
                try:
                    quota_data = await oauth_refresh.retrieve_account_quota(
                        account_dir=account_dir,
                        access_token=token,
                        proxy=proxy,
                        pool_account_id=acc_id,
                    )
                except Exception as e:
                    logger.debug(f"[mcp] Error retrieving quota for {acc_id}: {e}")

            res_accounts.append(
                {
                    "id": acc_id,
                    "label": acc.get("label"),
                    "proxy": acc.get("proxy"),
                    "active": acc_id == active_id if pool_manager.pool_enabled() else True,
                    "status": state.get("status", "healthy"),
                    "cooldown_until": state.get("cooldown_until"),
                    "consecutive_failures": state.get("consecutive_failures", 0),
                    "last_used_ts": state.get("last_used_ts"),
                    "total_requests": state.get("total_requests", 0),
                    "total_prompt_tokens": state.get("total_prompt_tokens", 0),
                    "total_completion_tokens": state.get("total_completion_tokens", 0),
                    "limits": quota_data,
                }
            )

        return {
            "pool_enabled": pool_manager.pool_enabled(),
            "active_account_id": active_id,
            "accounts_count": len(res_accounts),
            "accounts": res_accounts,
        }

    else:
        raise ValueError(f"Unknown tool: {name}")


@router.post("/mcp", summary="MCP JSON-RPC Endpoint")
async def mcp_jsonrpc_endpoint(request: Request):
    """MCP JSON-RPC 2.0 endpoint for AI agents (Claude Code, gclaude, cursor, etc.)."""
    _check_mcp_auth(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    if method == "initialize":
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": SERVER_INFO,
                },
            }
        )

    elif method == "notifications/initialized":
        return JSONResponse(content={"jsonrpc": "2.0", "result": {}})

    elif method == "tools/list":
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": AVAILABLE_TOOLS,
                },
            }
        )

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        try:
            result_data = await _handle_tool_call(tool_name, arguments)
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result_data, indent=2, ensure_ascii=False),
                            }
                        ],
                        "isError": False,
                    },
                }
            )
        except Exception as e:
            logger.error(f"[mcp] Tool call {tool_name} failed: {e}", exc_info=True)
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error executing {tool_name}: {str(e)}",
                            }
                        ],
                        "isError": True,
                    },
                }
            )

    elif method == "ping":
        return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {}})

    else:
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }
        )


@router.get("/mcp/sse", summary="MCP Server-Sent Events Endpoint")
async def mcp_sse_endpoint(request: Request):
    """MCP SSE endpoint for tools and agent discovery."""
    _check_mcp_auth(request)

    async def sse_event_stream():
        # Send initial endpoint event
        yield "event: endpoint\ndata: /mcp\n\n"
        while True:
            await asyncio.sleep(15)
            yield ": ping\n\n"

    return StreamingResponse(sse_event_stream(), media_type="text/event-stream")
