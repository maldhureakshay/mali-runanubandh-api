"""
Standardized API response structure.

Provides Pydantic models and helper functions to wrap and serialize all responses
returned from endpoints, maintaining a uniform format.
"""

from typing import Any, Generic, TypeVar
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """
    Standardized top-level API response envelope.
    """
    success: bool = Field(..., description="Indicates if the operation was successful")
    message: str = Field("", description="Human-readable summary message or error description")
    data: T | None = Field(None, description="Response payload data")
    meta: dict | None = Field(None, description="Optional metadata (e.g. pagination)")


def success_response(
    data: Any = None,
    message: str = "Operation completed successfully.",
    status_code: int = 200,
    meta: dict | None = None
) -> JSONResponse:
    """
    Generate a JSONResponse wrapping a successful payload.
    
    Args:
        data: The output payload/data.
        message: Success message.
        status_code: HTTP status code (defaults to 200).
        meta: Optional metadata like pagination cursors.
        
    Returns:
        JSONResponse: Configured with standard success response envelope.
    """
    content = {
        "success": True,
        "message": message,
        "data": data
    }
    if meta is not None:
        content["meta"] = meta
        
    return JSONResponse(content=content, status_code=status_code)


def error_response(
    message: str = "An error occurred.",
    status_code: int = 400,
    data: Any = None
) -> JSONResponse:
    """
    Generate a JSONResponse wrapping an error payload.
    
    Args:
        message: Error message.
        status_code: HTTP status code (defaults to 400).
        data: Optional additional debug details.
        
    Returns:
        JSONResponse: Configured with standard error response envelope.
    """
    content = {
        "success": False,
        "message": message,
        "data": data
    }
    return JSONResponse(content=content, status_code=status_code)
