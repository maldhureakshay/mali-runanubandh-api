"""
Like domain model.

Defines the structure of a like document and includes recommended database indexes.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

# =====================================================================
# MongoDB Recommended Indexes for Likes Collection
# =====================================================================
# 1. Unique compound index on postId and userId to ensure one like per user:
#    db.likes.create_index([("postId", 1), ("userId", 1)], unique=True)
# =====================================================================


class Like(BaseModel):
    """
    Domain model representing a post reaction (like).
    """
    model_config = ConfigDict(
        populate_by_name=True
    )

    @model_validator(mode="before")
    @classmethod
    def convert_object_id(cls, data: Any) -> Any:
        """Coerce MongoDB ObjectId into a string."""
        if isinstance(data, dict):
            if "_id" in data and not isinstance(data["_id"], str):
                data["_id"] = str(data["_id"])
        return data

    id: Optional[str] = Field(None, alias="_id", description="MongoDB ObjectId hex string")
    postId: str = Field(..., description="Target post ID which is liked")
    userId: str = Field(..., description="User ID of the person who liked the post")
    createdAt: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp when post was liked")
