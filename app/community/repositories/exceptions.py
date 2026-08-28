"""
Repository exceptions module.

Defines custom exceptions raised by the repository layer during database operations.
"""

from app.core.exceptions import AppException


class RepositoryException(AppException):
    """Base exception for all repository-level database errors."""
    def __init__(self, message: str, status_code: int = 500, data: dict | None = None) -> None:
        super().__init__(message=message, status_code=status_code, data=data)


class DocumentNotFoundException(RepositoryException):
    """Raised when a query fails to locate a required document in the database."""
    def __init__(self, message: str = "Requested database document was not found.") -> None:
        super().__init__(message=message, status_code=404)


class InvalidCursorException(RepositoryException):
    """Raised when an invalid pagination cursor is supplied."""
    def __init__(self, message: str = "The provided pagination cursor is invalid.") -> None:
        super().__init__(message=message, status_code=400)
