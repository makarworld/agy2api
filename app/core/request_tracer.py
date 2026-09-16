import contextvars
import json
from typing import Any, Optional


class RequestTrace:
    def __init__(self):
        self.raw_request: Optional[dict] = None
        self.raw_response: Optional[Any] = None
        self.response_status: Optional[int] = None
        self.pool_account: Optional[str] = None
        self.attempt_count: int = 0

    @property
    def raw_request_str(self) -> Optional[str]:
        if self.raw_request is None:
            return None
        if isinstance(self.raw_request, str):
            return self.raw_request
        return json.dumps(self.raw_request, ensure_ascii=False)

    @property
    def raw_response_str(self) -> Optional[str]:
        if self.raw_response is None:
            return None
        if isinstance(self.raw_response, str):
            return self.raw_response
        return json.dumps(self.raw_response, ensure_ascii=False)


_current_trace: contextvars.ContextVar[Optional[RequestTrace]] = contextvars.ContextVar("_current_trace", default=None)


def start_trace() -> RequestTrace:
    trace = RequestTrace()
    _current_trace.set(trace)
    return trace


def get_current_trace() -> Optional[RequestTrace]:
    return _current_trace.get()


def record_attempt(
    *,
    raw_request: Optional[dict] = None,
    raw_response: Optional[Any] = None,
    response_status: Optional[int] = None,
    pool_account: Optional[str] = None,
) -> None:
    trace = _current_trace.get()
    if trace is None:
        trace = start_trace()
    if raw_request is not None:
        trace.attempt_count += 1
        trace.raw_request = raw_request
    if raw_response is not None:
        trace.raw_response = raw_response
    if response_status is not None:
        trace.response_status = response_status
    if pool_account is not None:
        trace.pool_account = pool_account
