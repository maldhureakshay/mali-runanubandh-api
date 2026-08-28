"""
Post domain model.

Defines the structure of a post document, nested schemas (AuthorSnapshot, Content, Statistics,
Moderation, VisibilitySettings), metadata models, and validation logic.
Includes recommended MongoDB indexes documented as comments.
"""

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.community.enums import PostStatus, PostType, Visibility

# =====================================================================
# MongoDB Recommended Indexes for Posts Collection
# =====================================================================
# 1. Index on status:
#    db.posts.create_index([("status", 1)])
#
# 2. Index on authorId and status:
#    db.posts.create_index([("author.userId", 1), ("status", 1)])
#
# 3. Index on status and createdAt:
#    db.posts.create_index([("status", 1), ("createdAt", -1)])
#
# 4. Moderation indexes:
#    db.posts.create_index([("moderation.status", 1)])
#    db.posts.create_index([("moderation.status", 1), ("moderation.submittedAt", -1)])
#    db.posts.create_index([("moderation.status", 1), ("type", 1)])
#    db.posts.create_index([("moderation.status", 1), ("author.userId", 1)])
#
# 5. Community feed index (covers find_feed: status + visibility + sort by publishedAt):
#    db.posts.create_index(
#        [("moderation.status", 1), ("visibility.visibility", 1), ("publishedAt", -1)],
#        name="idx_feed_status_visibility_published"
#    )
#
# 6. Expiry index (sparse; supports expiresAt > now filtering for BIRTHDAY and
#    MARRIAGE_SUCCESS post types at the root document level):
#    db.posts.create_index(
#        [("expiresAt", 1)],
#        sparse=True,
#        name="idx_posts_expires_at"
#    )
# =====================================================================


class AuthorSnapshot(BaseModel):
    """
    Read-only snapshot of user profile details at the time of authoring the post.
    """
    model_config = ConfigDict(frozen=True)

    userId: str = Field(..., description="Firebase/User authentication unique ID")
    profileId: str = Field(..., description="Associated user matrimony profile ID")
    fullName: str = Field(..., description="Full name of the user")
    profileImage: Optional[str] = Field(None, description="URL to profile image snapshot")
    branch: Optional[str] = Field(None, description="Assigned community branch")
    city: Optional[str] = Field(None, description="City of residence")
    verified: bool = Field(False, description="Verification status of the profile")
    paidMember: bool = Field(False, description="Subscription status indicating active premium payment")


class Content(BaseModel):
    """
    Content payload of a post.
    """
    model_config = ConfigDict(frozen=True)

    title: Optional[str] = Field(None, description="Optional title header of the post")
    body: Optional[str] = Field(None, description="Primary textual content body")
    images: List[str] = Field(default_factory=list, description="Array of image urls uploaded with the post")


class Statistics(BaseModel):
    """
    Key engagement statistics for the post.
    """
    likesCount: int = Field(0, description="Total likes count")
    commentsCount: int = Field(0, description="Total comments count")
    viewsCount: int = Field(0, description="Total views count")
    reportsCount: int = Field(0, description="Total abuse/spam reports count")
    sharesCount: int = Field(0, description="Total shares count")





class Moderation(BaseModel):
    """
    Moderation history and current post approval status.
    """
    status: PostStatus = Field(PostStatus.DRAFT, description="Moderation workflow status")
    submittedAt: Optional[datetime] = Field(None, description="When it was submitted for review")
    reviewedAt: Optional[datetime] = Field(None, description="When it was reviewed")
    reviewedBy: Optional[str] = Field(None, description="Admin who reviewed")
    reviewComments: Optional[str] = Field(None, description="Comments from the reviewer")
    rejectionReason: Optional[str] = Field(None, description="Reason for rejection/needs changes")
    approvalNotes: Optional[str] = Field(None, description="Notes upon approval")
    version: int = Field(1, description="Post version number")
    resubmittedAt: Optional[datetime] = Field(None, description="When it was resubmitted")


class VisibilitySettings(BaseModel):
    """
    Post visibility configuration settings.
    """
    model_config = ConfigDict(frozen=True)

    visibility: Visibility = Field(Visibility.PUBLIC, description="Target visibility audience")


# =====================================================================
# Metadata Models
# =====================================================================

class SuccessStoryMetadata(BaseModel):
    """
    Metadata schema specific to SUCCESS_STORY type.
    """
    model_config = ConfigDict(frozen=True)

    partnerName: str = Field(..., description="Full name of the marriage partner")
    weddingDate: datetime = Field(..., description="UTC timestamp of the wedding date")
    weddingLocation: Optional[str] = Field(None, description="Location/venue of the wedding")


class PollOption(BaseModel):
    """
    Individual choice option for a POLL.
    """
    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique option identifier")
    text: str = Field(..., description="Choice option display text")
    votesCount: int = Field(0, description="Total vote count for this option")


class PollMetadata(BaseModel):
    """
    Metadata schema specific to POLL type.
    """
    model_config = ConfigDict(frozen=True)

    question: str = Field(..., description="The poll question text")
    options: List[PollOption] = Field(..., description="Available options in the poll")
    allowMultipleSelection: bool = Field(False, description="Flag indicating if multiple options can be chosen")
    expiresAt: Optional[datetime] = Field(None, description="UTC timestamp of when the poll expires")


class HelpRequestMetadata(BaseModel):
    """
    Metadata schema specific to HELP_REQUEST type.
    """
    model_config = ConfigDict(frozen=True)

    contactNumber: Optional[str] = Field(None, description="Contact phone number for quick assistance")
    urgent: bool = Field(False, description="Priority urgency tag")


class AnnouncementMetadata(BaseModel):
    """
    Metadata schema specific to ANNOUNCEMENT type.
    """
    model_config = ConfigDict(frozen=True)

    priority: str = Field("NORMAL", description="Announcement priority (e.g. HIGH, NORMAL)")
    expiresAt: Optional[datetime] = Field(None, description="UTC timestamp of announcement expiration")
    bannerImage: Optional[str] = Field(None, description="URL of announcement banner graphics")
    category: Optional[str] = Field(None, description="Announcement category (Event, Notice, etc.)")
    eventDate: Optional[datetime] = Field(None, description="UTC timestamp of the event")
    location: Optional[str] = Field(None, description="Event location")
    buttonName: Optional[str] = Field(None, description="Custom name for the button")
    buttonLink: Optional[str] = Field(None, description="URL link for the button")


class BirthdayMetadata(BaseModel):
    """
    Metadata schema specific to BIRTHDAY type.
    """
    model_config = ConfigDict(frozen=True)

    profileId: str = Field(..., description="Matrimony profile ID of the birthday user")
    profileName: str = Field("Community Member", description="Full name of the birthday user")
    birthdayDate: datetime = Field(..., description="UTC timestamp of the birthday date")


class ProfileSnapshot(BaseModel):
    """
    Enriched profile snapshot for display purposes, usually populated at read-time.
    """
    profileId: str
    fullName: str
    imageUrl: Optional[str] = None


class MarriageAnnouncementType(str, Enum):
    """Announcement sub-type for MARRIAGE_SUCCESS posts."""
    SINGLE_PERSON = "SINGLE_PERSON"
    COUPLE = "COUPLE"


class MarriageSuccessMetadata(BaseModel):
    """
    Metadata schema specific to MARRIAGE_SUCCESS type.

    SINGLE_PERSON: only person1ProfileId is stored; person2ProfileId must be absent.
    COUPLE:        both person1ProfileId and person2ProfileId are required.

    Only profile IDs are stored here. Name/image resolution happens at read time
    via the profile service and is intentionally outside Phase 1 scope.
    """
    model_config = ConfigDict(frozen=True)

    announcementType: MarriageAnnouncementType = Field(
        ..., description="Whether this is a single-person or couple announcement"
    )
    person1ProfileId: str = Field(
        ..., description="Matrimony profile ID of the first (or only) person"
    )
    person2ProfileId: Optional[str] = Field(
        None, description="Matrimony profile ID of the second person (required for COUPLE)"
    )
    person1Snapshot: Optional[ProfileSnapshot] = Field(
        None, description="Enriched snapshot of person 1 (populated at read-time)"
    )
    person2Snapshot: Optional[ProfileSnapshot] = Field(
        None, description="Enriched snapshot of person 2 (populated at read-time)"
    )

    @model_validator(mode="after")
    def validate_announcement_type_rules(self) -> "MarriageSuccessMetadata":
        """
        Enforce profile ID rules based on announcementType.
        """
        if self.announcementType == MarriageAnnouncementType.COUPLE:
            if not self.person2ProfileId or not self.person2ProfileId.strip():
                raise ValueError(
                    "person2ProfileId is required when announcementType is COUPLE."
                )
        elif self.announcementType == MarriageAnnouncementType.SINGLE_PERSON:
            if self.person2ProfileId is not None:
                raise ValueError(
                    "person2ProfileId must be null/absent when announcementType is SINGLE_PERSON."
                )
        return self


# Discriminator union type for type-safe metadata parsing
PostMetadata = Union[
    SuccessStoryMetadata,
    PollMetadata,
    HelpRequestMetadata,
    AnnouncementMetadata,
    BirthdayMetadata,
    MarriageSuccessMetadata,
    None
]



# =====================================================================
# Core Post Model
# =====================================================================

class Post(BaseModel):
    """
    Domain model representing a Community Post.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

    @model_validator(mode="before")
    @classmethod
    def convert_object_id(cls, data: Any) -> Any:
        """Coerce MongoDB ObjectId into a string for Pydantic string validation."""
        if isinstance(data, dict):
            if "_id" in data and not isinstance(data["_id"], str):
                data["_id"] = str(data["_id"])
        return data

    id: Optional[str] = Field(None, alias="_id", description="MongoDB ObjectId hex string")
    type: PostType = Field(..., description="Categorical type of post (POST, POLL, etc.)")
    author: AuthorSnapshot = Field(..., description="Snapshot of the publishing author details")
    content: Content = Field(..., description="Post content text/images payload")
    metadata: PostMetadata = Field(None, description="Specialized metadata depending on PostType")
    statistics: Statistics = Field(default_factory=Statistics, description="Counters tracking user interaction")
    visibility: VisibilitySettings = Field(default_factory=VisibilitySettings, description="Audience visibility details")
    
    moderation: Moderation = Field(default_factory=Moderation, description="Post moderation and approval stats")
    createdAt: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of post creation")
    updatedAt: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of last update")
    publishedAt: Optional[datetime] = Field(None, description="UTC timestamp when the post was approved and published")
    expiresAt: Optional[datetime] = Field(None, description="UTC timestamp of post expiration")


    @model_validator(mode="after")
    def validate_post_type_rules(self) -> "Post":
        """
        Validate domain rules mapping to PostType fields and structures.
        """
        post_type = self.type
        content = self.content
        metadata = self.metadata

        # Standard post validation
        if post_type == PostType.POST:
            if not content.body or not content.body.strip():
                raise ValueError("body is required for standard POST type.")

        # Success story validation
        elif post_type == PostType.SUCCESS_STORY:
            if not content.body or not content.body.strip():
                raise ValueError("body is required for SUCCESS_STORY type.")
            if not content.images or len(content.images) < 1:
                raise ValueError("at least one image is required for SUCCESS_STORY type.")
            if not isinstance(metadata, SuccessStoryMetadata):
                raise ValueError("metadata must conform to SuccessStoryMetadata for SUCCESS_STORY type.")
            if not metadata.partnerName or not metadata.partnerName.strip():
                raise ValueError("partnerName is required for SUCCESS_STORY type.")
            if not metadata.weddingDate:
                raise ValueError("weddingDate is required for SUCCESS_STORY type.")

        # Poll validation
        elif post_type == PostType.POLL:
            if not isinstance(metadata, PollMetadata):
                raise ValueError("metadata must conform to PollMetadata for POLL type.")
            if not metadata.options or not (2 <= len(metadata.options) <= 6):
                raise ValueError("POLL must contain minimum 2 and maximum 6 options.")
            for opt in metadata.options:
                if not opt.text or not opt.text.strip():
                    raise ValueError("every option in a POLL must contain text.")

        # Help request validation
        elif post_type == PostType.HELP_REQUEST:
            if not content.body or not content.body.strip():
                raise ValueError("body is required for HELP_REQUEST type.")
            if metadata is not None and not isinstance(metadata, HelpRequestMetadata):
                raise ValueError("metadata must conform to HelpRequestMetadata for HELP_REQUEST type.")

        # Announcement validation
        elif post_type == PostType.ANNOUNCEMENT:
            if not content.body or not content.body.strip():
                raise ValueError("body is required for ANNOUNCEMENT type.")
            if metadata is not None and not isinstance(metadata, AnnouncementMetadata):
                raise ValueError("metadata must conform to AnnouncementMetadata for ANNOUNCEMENT type.")

        # Birthday validation
        elif post_type == PostType.BIRTHDAY:
            if not isinstance(metadata, BirthdayMetadata):
                raise ValueError("metadata must conform to BirthdayMetadata for BIRTHDAY type.")
            if not metadata.profileId or not metadata.profileId.strip():
                raise ValueError("profileId is required for BIRTHDAY type.")
            if not metadata.birthdayDate:
                raise ValueError("birthdayDate is required for BIRTHDAY type.")
            
            # Calculate expiresAt: start of next calendar day in IST (UTC+5:30)
            from datetime import timezone, timedelta
            ist = timezone(timedelta(hours=5, minutes=30))
            bdate = metadata.birthdayDate
            birthday_ist = bdate.astimezone(ist) if bdate.tzinfo else bdate.replace(tzinfo=timezone.utc).astimezone(ist)
            next_day_ist = datetime(birthday_ist.year, birthday_ist.month, birthday_ist.day, tzinfo=ist) + timedelta(days=1)
            self.expiresAt = next_day_ist.astimezone(timezone.utc)

        # Marriage success validation
        elif post_type == PostType.MARRIAGE_SUCCESS:
            if not isinstance(metadata, MarriageSuccessMetadata):
                raise ValueError(
                    "metadata must conform to MarriageSuccessMetadata for MARRIAGE_SUCCESS type."
                )
            if not metadata.person1ProfileId or not metadata.person1ProfileId.strip():
                raise ValueError("person1ProfileId is required for MARRIAGE_SUCCESS type.")

            # Set expiration: 30 days from creation time
            from datetime import timezone, timedelta
            self.expiresAt = self.createdAt.replace(tzinfo=timezone.utc) + timedelta(days=30) \
                if self.createdAt.tzinfo is None \
                else self.createdAt + timedelta(days=30)

        return self

