"""
Comment domain model.

Defines the structure of a comment document and includes recommended database indexes.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.community.models.post import AuthorSnapshot

# =====================================================================
# MongoDB Recommended Indexes for Comments Collection
# =====================================================================
# 1. Compound index on postId and createdAt for paging comments:
#    db.comments.create_index([("postId", 1), ("createdAt", 1)])
# =====================================================================


class Comment(BaseModel):
    """
    Domain model representing a comment on a community post.
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
    postId: str = Field(..., description="Target post ID which is commented on")
    author: AuthorSnapshot = Field(..., description="Details of the comment author")
    comment: str = Field(..., description="Text content body of the comment")
    edited: bool = Field(False, description="Flag indicating if the comment was edited")
    createdAt: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of comment creation")
    updatedAt: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of last update")
    deletedAt: Optional[datetime] = Field(None, description="UTC timestamp when the comment was soft deleted")
