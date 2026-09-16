import httpx

from app.core.cloudcode_common import CLOUDCODE_BASE, cloudcode_headers
from app.core.proxy_config import httpx_client_kwargs

LIFECYCLE_PATHS = {
    "load-code-assist": "loadCodeAssist",
    "fetch-admin-controls": "fetchAdminControls",
    "fetch-available-models": "fetchAvailableModels",
    "fetch-user-info": "fetchUserInfo",
    "list-experiments": "listExperiments",
    "retrieve-user-quota-summary": "retrieveUserQuotaSummary",
}


def har_payload(operation: str, project_id: str, payload: dict) -> dict:
    if operation == "load-code-assist":
        return {"metadata": {"ideType": "ANTIGRAVITY"}}
    if operation in {
        "fetch-admin-controls",
        "fetch-available-models",
        "fetch-user-info",
        "list-experiments",
        "retrieve-user-quota-summary",
    }:
        return {"project": project_id}
    return payload


async def call_lifecycle(
    operation: str,
    token: str,
    proxy: str | None,
    project_id: str,
    payload: dict,
) -> dict:
    method = LIFECYCLE_PATHS[operation]
    async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=60.0)) as client:
        response = await client.post(
            f"{CLOUDCODE_BASE}/v1internal:{method}",
            headers=cloudcode_headers(token),
            json=har_payload(operation, project_id, payload),
        )
    response.raise_for_status()
    return response.json() if response.content else {}
