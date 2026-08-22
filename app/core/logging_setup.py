import logging
import logging.handlers
import os
import uuid
import contextvars

# Mặc định là 'no-trace' khi không nằm trong một request
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="no-trace")

class TraceLogFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = trace_id_var.get()
        return True

def setup_logging():
    log_format = "%(asctime)s | %(levelname)-7s | [%(trace_id)s] | %(name)s:%(funcName)s - %(message)s"

    formatter = logging.Formatter(log_format)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(TraceLogFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    root_logger.addHandler(handler)

    # Also write to a local rotating file so /v1/logs works without journalctl
    # (e.g. local dev on Windows, where journalctl doesn't exist at all).
    log_file_path = os.environ.get("AGY_LOG_FILE_PATH", "app/data/agy2api.log")
    os.makedirs(os.path.dirname(log_file_path) or ".", exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(TraceLogFilter())
    root_logger.addHandler(file_handler)
    
    # Apply filter to uvicorn loggers to ensure they don't crash if they try to log with our formatter
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        l = logging.getLogger(logger_name)
        if not any(isinstance(f, TraceLogFilter) for f in l.filters):
            l.addFilter(TraceLogFilter())
