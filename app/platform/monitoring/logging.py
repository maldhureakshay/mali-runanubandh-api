"""
Structured Logging context.

Defines contextvars to store request-scoped data like requestId and userId.
"""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, Optional

# Context variables for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")


def get_request_id() -> str:
    """Return current request ID."""
    return request_id_var.get()


def get_user_id() -> str:
    """Return current user ID."""
    return user_id_var.get()


class StructuredLogFormatter(logging.Formatter):
    """
    Log formatter that injects requestId, userId, and structured keys.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON-like structured string."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "requestId": get_request_id(),
            "userId": get_user_id()
        }

        # Include execution details if present
        if hasattr(record, "endpoint"):
            log_data["endpoint"] = getattr(record, "endpoint")
        if hasattr(record, "executionTime"):
            log_data["executionTime"] = getattr(record, "executionTime")
        if hasattr(record, "statusCode"):
            log_data["statusCode"] = getattr(record, "statusCode")

        # Fallback to string representation if json dumps fails
        try:
            return json.dumps(log_data)
        except Exception:
            return str(log_data)
