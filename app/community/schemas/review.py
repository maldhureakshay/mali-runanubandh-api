"""
Post Review schema.

Defines Pydantic schemas for the review history API endpoints.
"""

from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

from app.community.enums import PostStatus


class PostReviewResponse(BaseModel):
    """
    API Response schema for a single post review record.
    """
    @model_validator(mode="before")
    @classmethod
    def coerce_id(cls, data: Any) -> Any:
        """Coerce ObjectId to string."""
        if isinstance(data, dict):
            if "_id" in data and not isinstance(data["_id"], str):
                data["_id"] = str(data["_id"])
        return data

    id: str = Field(..., alias="_id", description="MongoDB hex string identifier for this review")
    action: str = Field(..., description="Action taken, e.g. POST_APPROVED")
    statusBefore: PostStatus = Field(..., description="Status of the post before the action")
    statusAfter: PostStatus = Field(..., description="Status of the post after the action")
    moderatorId: Optional[str] = Field(None, description="ID of the moderator/admin taking action")
    createdAt: datetime = Field(..., description="Timestamp of the action")
    reviewComments: Optional[str] = Field(None, description="Moderator feedback for the author")
    approvalNotes: Optional[str] = Field(None, description="Internal notes regarding approval")
    rejectionReason: Optional[str] = Field(None, description="Brief rejection reason")
    postVersion: int = Field(..., description="Version of the post at the time of the action")
