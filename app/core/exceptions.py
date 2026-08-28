"""
Centralized exception handling module.

Defines domain-specific application exceptions and register handlers
to intercept errors globally and format them into the standard APIResponse template.
"""

import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.responses import error_response

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception from which all domain-specific errors inherit."""
    def __init__(self, message: str, status_code: int = 500, data: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.data = data


class NotFoundException(AppException):
    """Exception raised when a requested resource is not found."""
    def __init__(self, message: str = "Resource not found.", data: dict | None = None) -> None:
        super().__init__(message=message, status_code=404, data=data)


class BadRequestException(AppException):
    """Exception raised for invalid requests or business rules violations."""
    def __init__(self, message: str = "Bad request.", data: dict | None = None) -> None:
        super().__init__(message=message, status_code=400, data=data)


class UnauthorizedException(AppException):
    """Exception raised when authentication fails or is missing."""
    def __init__(self, message: str = "Unauthorized access.", data: dict | None = None) -> None:
        super().__init__(message=message, status_code=401, data=data)


class ForbiddenException(AppException):
    """Exception raised when user does not have permissions to access resource."""
    def __init__(self, message: str = "Access forbidden.", data: dict | None = None) -> None:
        super().__init__(message=message, status_code=403, data=data)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Registers custom exception handlers on the FastAPI application instance.
    
    Transforms exceptions into standardized API responses.
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.error("AppException occurred: %s (Status: %s)", exc.message, exc.status_code)
        return error_response(message=exc.message, status_code=exc.status_code, data=exc.data)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.error("Validation error: %s", exc.errors())
        # Format the validation errors into a readable structure
        details = exc.errors()
        message = "Validation failed."
        if details:
            # Pick the first error's msg to show as the main message, if present
            message = f"Validation failed: {details[0].get('msg', 'Invalid input')}"
        return error_response(message=message, status_code=422, data={"errors": details})

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        logger.error("HTTPException occurred: %s (Status: %s)", exc.detail, exc.status_code)
        return error_response(message=exc.detail, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled internal exception occurred: %s", str(exc))
        return error_response(
            message="An internal server error occurred. Please try again later.",
            status_code=500
        )
