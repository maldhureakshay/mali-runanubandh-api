from typing import Generic, TypeVar, List
from pydantic import BaseModel

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standardized wrapper for paginated API responses.
    This structure simplifies client-side table/scroll rendering.
    """
    data: List[T]
    total: int
    page: int
    limit: int
    has_more: bool
