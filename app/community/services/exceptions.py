"""
Service exceptions module.

Defines custom exceptions raised by the service layer during business logic processing.
"""

from app.core.exceptions import AppException


class ServiceException(AppException):
    """Base exception for all service-level operations."""
    def __init__(self, message: str, status_code: int = 400, data: dict | None = None) -> None:
        super().__init__(message=message, status_code=status_code, data=data)


class PostNotFoundException(ServiceException):
    """Raised when a specific post cannot be found or is deleted."""
    def __init__(self, message: str = "The requested post does not exist or has been deleted.") -> None:
        super().__init__(message=message, status_code=404)


class CommentNotFoundException(ServiceException):
    """Raised when a specific comment cannot be found."""
    def __init__(self, message: str = "The requested comment does not exist.") -> None:
        super().__init__(message=message, status_code=404)


class InvalidPostTypeException(ServiceException):
    """Raised when a post type is invalid or unsupported."""
    def __init__(self, message: str = "The provided post type is invalid.") -> None:
        super().__init__(message=message, status_code=400)


class DuplicateLikeException(ServiceException):
    """Raised when a user attempts to like a post they have already liked."""
    def __init__(self, message: str = "You have already liked this post.") -> None:
        super().__init__(message=message, status_code=409)


class DuplicateReportException(ServiceException):
    """Raised when a user attempts to report a post they have already reported."""
    def __init__(self, message: str = "You have already reported this post.") -> None:
        super().__init__(message=message, status_code=409)


class ValidationException(ServiceException):
    """Raised when request inputs fail business rules validation checks."""
    def __init__(self, message: str = "Validation failed.", data: dict | None = None) -> None:
        super().__init__(message=message, status_code=422, data=data)


class PostDeletedException(ServiceException):
    """Raised when attempting to interact with a post that has been deleted."""
    def __init__(self, message: str = "Cannot perform operation on a deleted post.") -> None:
        super().__init__(message=message, status_code=400)


class DuplicateVoteException(ServiceException):
    """Raised when a user attempts to vote in a poll they have already voted in."""
    def __init__(self, message: str = "You have already voted in this poll.") -> None:
        super().__init__(message=message, status_code=409)


class PollExpiredException(ServiceException):
    """Raised when a user attempts to vote in an expired poll."""
    def __init__(self, message: str = "This poll has expired.") -> None:
        super().__init__(message=message, status_code=400)


class InvalidPostStateException(ServiceException):
    """Raised when attempting a state transition that is not allowed for the post's current status."""
    def __init__(self, message: str = "Invalid state transition for post.") -> None:
        super().__init__(message=message, status_code=409)
