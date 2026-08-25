"""
Rate Limit Middleware.

Protects API endpoints by enforcing request limits using sliding-window rate limits per user/IP/endpoint.
"""

import hashlib
import logging
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.platform.rate_limit.limiter import InMemRateLimiter

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware applying Rate Limits per client IP or authenticated Bearer token per endpoint.
    """

    def __init__(self, app, limiter: InMemRateLimiter) -> None:
        """
        Constructor accepts FastAPI app instance and InMemRateLimiter instance.
        """
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        
        # Exclude Swagger documents and health probes from rate limits
        if path in ("/docs", "/redoc", "/openapi.json") or path.startswith("/health"):
            return await call_next(request)

        # Build user identity key based on Bearer token (if present) or Client IP
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token_part = auth_header[7:]
            # Hash to keep keys short and secure
            token_hash = hashlib.sha256(token_part.encode("utf-8")).hexdigest()
            client_id = f"user:{token_hash[:16]}"
        else:
            client_id = f"ip:{request.client.host if request.client else 'unknown'}"

        # Key composition: rate_limit:{client}:{method}:{path}
        limit_key = f"rate_limit:{client_id}:{request.method}:{path}"

        if await self._limiter.is_rate_limited(limit_key):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests. Please try again later."}
            )

        return await call_next(request)
