"""
Post Schemas module.

Defines Pydantic request and response schemas for validating incoming Post data and formatting API output.
"""

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field, AliasPath, model_validator

from app.community.enums import PostStatus, PostType
from app.community.models.post import (
    AuthorSnapshot,
    Content,
    PostMetadata,
    Statistics,
    VisibilitySettings,
    MarriageSuccessMetadata,
)

class PostCreate(BaseModel):
    """
    Request payload schema for creating a new post.
    """
    type: PostType = Field(..., description="Categorical type of post (POST, POLL, SUCCESS_STORY, etc.)")
    content: Content = Field(..., description="Post payload containing textual/media information")
    metadata: Optional[PostMetadata] = Field(None, description="Metadata schema depending on PostType")
    visibility: VisibilitySettings = Field(default_factory=VisibilitySettings, description="Audience visibility details")
    status: Optional[PostStatus] = Field(None, description="Initial post status, e.g. DRAFT")

    @model_validator(mode="after")
    def reject_restricted_types(self) -> "PostCreate":
        """Prevent clients from directly creating system/admin-only post types."""
        if self.type == PostType.BIRTHDAY:
            raise ValueError("Birthday posts cannot be created by clients directly.")
        if self.type == PostType.MARRIAGE_SUCCESS:
            raise ValueError("Marriage success posts cannot be created by clients directly.")
        return self



class PostUpdate(BaseModel):
    """
    Request payload schema for updating an existing post.
    """
    content: Optional[Content] = Field(None, description="Updated post body/images")
    metadata: Optional[PostMetadata] = Field(None, description="Updated metadata matching PostType")
    visibility: Optional[VisibilitySettings] = Field(None, description="Updated visibility options")
    status: Optional[PostStatus] = Field(None, description="Updated status, e.g. DRAFT")


class PostResponse(BaseModel):
    """
    API Response schema for community posts.
    """
    @model_validator(mode="before")
    @classmethod
    def populate_flat_stats(cls, data: Any) -> Any:
        """Coerce ObjectId and populate flat statistics fields from nested statistics."""
        if isinstance(data, dict):
            if "_id" in data and not isinstance(data["_id"], str):
                data["_id"] = str(data["_id"])
            stats = data.get("statistics")
            if isinstance(stats, dict):
                data.setdefault("likesCount", stats.get("likesCount", 0))
                data.setdefault("commentsCount", stats.get("commentsCount", 0))
                data.setdefault("viewsCount", stats.get("viewsCount", 0))
                data.setdefault("reportsCount", stats.get("reportsCount", 0))
            elif hasattr(stats, "likesCount"):
                data.setdefault("likesCount", getattr(stats, "likesCount", 0))
                data.setdefault("commentsCount", getattr(stats, "commentsCount", 0))
                data.setdefault("viewsCount", getattr(stats, "viewsCount", 0))
                data.setdefault("reportsCount", getattr(stats, "reportsCount", 0))
        return data

    id: str = Field(..., alias="_id", description="MongoDB hex string identifier")
    type: PostType
    author: AuthorSnapshot
    content: Content
    metadata: Optional[PostMetadata] = None
    statistics: Statistics
    visibility: VisibilitySettings
    createdAt: datetime
    updatedAt: datetime
    publishedAt: Optional[datetime] = None
    expiresAt: Optional[datetime] = None

    status: PostStatus = Field(..., validation_alias=AliasPath("moderation", "status"), description="Simplified post status")
    submittedAt: Optional[datetime] = Field(None, validation_alias=AliasPath("moderation", "submittedAt"))
    reviewedAt: Optional[datetime] = Field(None, validation_alias=AliasPath("moderation", "reviewedAt"))
    reviewedBy: Optional[str] = Field(None, validation_alias=AliasPath("moderation", "reviewedBy"))
    reviewComments: Optional[str] = Field(None, validation_alias=AliasPath("moderation", "reviewComments"))
    rejectionReason: Optional[str] = Field(None, validation_alias=AliasPath("moderation", "rejectionReason"))
    approvalNotes: Optional[str] = Field(None, validation_alias=AliasPath("moderation", "approvalNotes"))
    version: int = Field(1, validation_alias=AliasPath("moderation", "version"))
    resubmittedAt: Optional[datetime] = Field(None, validation_alias=AliasPath("moderation", "resubmittedAt"))
    
    # Flat statistics exposed at root level
    likesCount: int = Field(0, description="Total likes count")
    commentsCount: int = Field(0, description="Total comments count")
    viewsCount: int = Field(0, description="Total views count")
    reportsCount: int = Field(0, description="Total reports count")
    
    # Liking status for authenticated requests
    likedByCurrentUser: bool = Field(False, description="Whether the authenticated user liked this post")
    
    # Voting status for authenticated requests (only populated for PostType = POLL)
    hasVoted: bool = Field(False, description="Whether the authenticated user has voted on this poll")
    selectedOptions: List[str] = Field(default_factory=list, description="The option IDs selected by the authenticated user")
