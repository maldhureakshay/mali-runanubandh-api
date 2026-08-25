"""
Performance & Request ID Middleware.

Tracks HTTP request durations, manages request ID contexts, and performs structured timing logs.
"""

import logging
import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.platform.monitoring.logging import request_id_var, user_id_var
from config import settings

logger = logging.getLogger(__name__)


class MonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware executing Request ID propagation, structured logging context,
    latency performance timing, and slow requests alerts.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Read or generate Request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Set context variables
        request_id_token = request_id_var.set(request_id)
        
        # Try to resolve user ID from authenticated dependencies if already parsed,
        # or defaults to empty. (Can be updated dynamically during request processing)
        user_id_token = user_id_var.set("")

        start_time = time.time()
        status_code = 500
        
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            
            # Attach X-Request-ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            endpoint = f"{request.method} {request.url.path}"
            
            # Log structured request details using extra parameters
            extra = {
                "endpoint": endpoint,
                "executionTime": f"{duration_ms}ms",
                "statusCode": status_code
            }
            
            # Log structured entry
            logger.info("Request completed", extra=extra)

            # Performance Timing Alert: Log slow requests exceeding threshold
            threshold_ms = settings.PERFORMANCE_THRESHOLD_MS
            if duration_ms > threshold_ms:
                logger.warning(
                    "Slow Request Detected: %s took %dms (Threshold: %dms)",
                    endpoint,
                    duration_ms,
                    threshold_ms,
                    extra=extra
                )
                
            # Clear context variables
            request_id_var.reset(request_id_token)
            user_id_var.reset(user_id_token)
