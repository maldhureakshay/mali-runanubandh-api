"""
Post Review model.

Defines the database schema for the post review history.
"""

from typing import Any, Dict, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict, model_validator

from app.community.enums import PostStatus


# =====================================================================
# Database Indexes
# =====================================================================
# MongoDB collections should be indexed for querying performance:
#    db.post_reviews.create_index("postId")
#    db.post_reviews.create_index("createdAt")
#    db.post_reviews.create_index([("postId", 1), ("createdAt", 1)])
#    db.post_reviews.create_index("moderatorId")
#    db.post_reviews.create_index("action")
# =====================================================================


class PostReview(BaseModel):
    """
    Append-only record of a moderation action taken on a post.
    """
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def convert_object_id(cls, data: Any) -> Any:
        """Coerce MongoDB ObjectId into a string."""
        if isinstance(data, dict):
            if "_id" in data and not isinstance(data["_id"], str):
                data["_id"] = str(data["_id"])
        return data

    id: Optional[str] = Field(None, alias="_id", description="MongoDB hex string identifier")
    postId: str = Field(..., description="ID of the post that was moderated")
    postVersion: int = Field(..., description="Version of the post at the time of moderation")
    authorId: str = Field(..., description="ID of the post author")
    moderatorId: Optional[str] = Field(None, description="ID of the moderator/admin taking action, if applicable")
    
    action: str = Field(..., description="Event action name, e.g. POST_APPROVED, POST_NEEDS_CHANGES")
    statusBefore: PostStatus = Field(..., description="Status of the post before the action")
    statusAfter: PostStatus = Field(..., description="Status of the post after the action")
    
    reviewComments: Optional[str] = Field(None, description="Moderator feedback for the author")
    approvalNotes: Optional[str] = Field(None, description="Internal notes regarding approval")
    rejectionReason: Optional[str] = Field(None, description="Brief rejection reason")
    
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of this action")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Any extra metadata")
