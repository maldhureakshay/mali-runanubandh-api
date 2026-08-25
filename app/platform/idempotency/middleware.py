"""
Idempotency Middleware.

Intercepts requests containing the 'Idempotency-Key' header, deduplicating processing loops.
"""

import json
import logging
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.platform.idempotency.service import IdempotencyService

logger = logging.getLogger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware providing transparent POST/PUT deduplication via the Idempotency-Key header.
    """

    def __init__(self, app, idempotency_service: IdempotencyService) -> None:
        """
        Constructor injects IdempotencyService.
        """
        super().__init__(app)
        self._service = idempotency_service

    async def dispatch(self, request: Request, call_next) -> Response:
        # Idempotency checks only apply to state-modifying requests (POST/PUT)
        if request.method not in ("POST", "PUT"):
            return await call_next(request)

        key = request.headers.get("Idempotency-Key")
        if not key:
            return await call_next(request)

        logger.info("Intercepted request with Idempotency-Key: %s", key)

        # Attempt to acquire lock (set key to PENDING)
        success = await self._service.start_request(key)
        if not success:
            # Key exists in cache, check its state
            cached = await self._service.get_response(key)
            if cached:
                status_code, headers, body = cached
                if body == "PENDING":
                    logger.warning("Duplicate request for key %s is currently PENDING execution.", key)
                    return JSONResponse(
                        status_code=status.HTTP_409_CONFLICT,
                        content={"detail": "Request already in progress. Please retry later."}
                    )
                logger.info("Serving cached idempotent response for key: %s (status: %d)", key, status_code)
                return JSONResponse(status_code=status_code, content=body, headers=headers)
            else:
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={"detail": "Idempotent request conflict. Please try again."}
                )

        # Successfully reserved key (lock is held), execute request pipeline
        try:
            response: Response = await call_next(request)
            
            # Capture and read response body to cache it safely
            body_bytes = b""
            async for chunk in response.body_iterator:
                body_bytes += chunk

            # Re-create the body iterator so subsequent ASGI handlers/clients can read it
            async def body_iterator():
                yield body_bytes
            response.body_iterator = body_iterator()

            # Attempt to parse body as JSON for structured storage
            try:
                decoded_body = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                decoded_body = body_bytes.decode("utf-8", errors="ignore")

            # Cache the response for future retries
            await self._service.save_response(
                key=key,
                status_code=response.status_code,
                headers=dict(response.headers),
                body=decoded_body
            )
            return response
        except Exception as e:
            # Evict lock on crash so client can retry
            await self._service._cache.delete(f"idempotency:{key}")
            logger.error("Error executing idempotent request %s, removed lock: %s", key, e, exc_info=True)
            raise e
