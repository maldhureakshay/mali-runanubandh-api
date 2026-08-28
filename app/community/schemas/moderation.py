from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field, AliasPath, model_validator

from app.community.enums import PostStatus, PostType, Visibility
from app.community.models.post import (
    AuthorSnapshot,
    Content,
    MarriageAnnouncementType,
    PostMetadata,
    VisibilitySettings,
)

class PendingPostSummaryResponse(BaseModel):
    """
    Summary representation of a pending post in the moderation queue.
    """
    @model_validator(mode="before")
    @classmethod
    def populate_flat_stats(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "_id" in data and not isinstance(data["_id"], str):
                data["_id"] = str(data["_id"])
            stats = data.get("statistics")
            if isinstance(stats, dict):
                data.setdefault("reportsCount", stats.get("reportsCount", 0))
            elif hasattr(stats, "reportsCount"):
                data.setdefault("reportsCount", getattr(stats, "reportsCount", 0))
        return data

    id: str = Field(..., alias="_id", description="Post ID")
    type: PostType = Field(..., description="Post Type")
    status: PostStatus = Field(..., validation_alias=AliasPath("moderation", "status"), description="Current moderation status")
    title: Optional[str] = Field(None, validation_alias=AliasPath("content", "title"), description="Post Title")
    body: Optional[str] = Field(None, validation_alias=AliasPath("content", "body"), description="Post Body")
    images: Optional[List[str]] = Field(None, validation_alias=AliasPath("content", "images"), description="Post Images")
    authorName: str = Field(..., validation_alias=AliasPath("author", "fullName"), description="Author full name")
    authorId: str = Field(..., validation_alias=AliasPath("author", "userId"), description="Author user ID")
    authorAvatar: Optional[str] = Field(None, validation_alias=AliasPath("author", "profileImage"), description="Author profile image URL")
    createdAt: Optional[datetime] = Field(None, description="Creation timestamp")
    submittedAt: Optional[datetime] = Field(None, validation_alias=AliasPath("moderation", "submittedAt"), description="Submission timestamp")
    version: int = Field(1, validation_alias=AliasPath("moderation", "version"), description="Post version")
    totalImages: int = Field(0, description="Total images in post")
    visibility: Visibility = Field(..., validation_alias=AliasPath("visibility", "visibility"), description="Post visibility settings")
    reportsCount: int = Field(0, description="Number of reports against this post")
    metadata: Optional[PostMetadata] = Field(None, description="Metadata schema depending on PostType")
    
    @model_validator(mode="before")
    @classmethod
    def calculate_total_images(cls, data: Any) -> Any:
        if isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, dict):
                images = content.get("images", [])
                data["totalImages"] = len(images) if images else 0
            elif hasattr(content, "images"):
                data["totalImages"] = len(getattr(content, "images", []))
        return data


class ModerationPostDetailsResponse(BaseModel):
    """
    Detailed representation of a post for moderation review.
    """
    @model_validator(mode="before")
    @classmethod
    def populate_flat_stats(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "_id" in data and not isinstance(data["_id"], str):
                data["_id"] = str(data["_id"])
            stats = data.get("statistics")
            if isinstance(stats, dict):
                data.setdefault("reportsCount", stats.get("reportsCount", 0))
            elif hasattr(stats, "reportsCount"):
                data.setdefault("reportsCount", getattr(stats, "reportsCount", 0))
        return data

    id: str = Field(..., alias="_id", description="Post ID")
    type: PostType = Field(..., description="Post Type")
    status: PostStatus = Field(..., validation_alias=AliasPath("moderation", "status"), description="Current moderation status")
    author: AuthorSnapshot = Field(..., description="Author snapshot details")
    content: Content = Field(..., description="Full post content including images")
    metadata: Optional[PostMetadata] = Field(None, description="Detailed metadata based on post type")
    submittedAt: Optional[datetime] = Field(None, validation_alias=AliasPath("moderation", "submittedAt"), description="Submission timestamp")
    version: int = Field(1, validation_alias=AliasPath("moderation", "version"), description="Post version")
    reportsCount: int = Field(0, description="Number of reports against this post")


class ApprovePostRequest(BaseModel):
    """
    Request payload schema for approving a post.
    """
    approvalNotes: Optional[str] = Field(None, max_length=500, description="Optional moderator note")


class NeedsChangesRequest(BaseModel):
    """
    Request payload schema for requesting changes on a post.
    """
    reviewComments: str = Field(..., min_length=20, max_length=2000, description="Required moderator feedback")
    rejectionReason: Optional[str] = Field(None, max_length=500, description="Optional brief rejection reason")


class CreateMarriageAnnouncementRequest(BaseModel):
    """
    Request payload for an admin creating a MARRIAGE_SUCCESS post.
    """
    announcementType: MarriageAnnouncementType = Field(
        ..., description="SINGLE_PERSON or COUPLE"
    )
    person1ProfileId: str = Field(
        ..., min_length=1, description="Profile ID of person 1"
    )
    person2ProfileId: Optional[str] = Field(
        None, description="Profile ID of person 2 — required for COUPLE, must be absent for SINGLE_PERSON"
    )
    content: Content = Field(
        ..., description="Post content (title / body / images)"
    )
    visibility: Optional[Visibility] = Field(
        Visibility.PUBLIC, description="Feed visibility (defaults to PUBLIC)"
    )

    @model_validator(mode="after")
    def validate_person2_rules(self) -> "CreateMarriageAnnouncementRequest":
        """Enforce person2 rules consistent with MarriageSuccessMetadata."""
        if self.announcementType == MarriageAnnouncementType.COUPLE:
            if not self.person2ProfileId or not self.person2ProfileId.strip():
                raise ValueError(
                    "person2ProfileId is required when announcementType is COUPLE."
                )
            if self.person1ProfileId == self.person2ProfileId:
                raise ValueError(
                    "person1ProfileId and person2ProfileId must be different."
                )
        elif self.announcementType == MarriageAnnouncementType.SINGLE_PERSON:
            if self.person2ProfileId is not None:
                raise ValueError(
                    "person2ProfileId must be null when announcementType is SINGLE_PERSON."
                )
        return self
