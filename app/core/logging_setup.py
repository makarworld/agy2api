import logging
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
    
    # Apply filter to uvicorn loggers to ensure they don't crash if they try to log with our formatter
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        l = logging.getLogger(logger_name)
        if not any(isinstance(f, TraceLogFilter) for f in l.filters):
            l.addFilter(TraceLogFilter())
