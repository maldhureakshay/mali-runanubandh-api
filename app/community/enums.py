"""
Community module enums.

Defines status, type, visibility, and reporting category enumerations.
"""

from enum import Enum


class PostType(str, Enum):
    """Types of community posts."""
    POST = "POST"
    SUCCESS_STORY = "SUCCESS_STORY"
    POLL = "POLL"
    HELP_REQUEST = "HELP_REQUEST"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    BIRTHDAY = "BIRTHDAY"
    MARRIAGE_SUCCESS = "MARRIAGE_SUCCESS"



class PostStatus(str, Enum):
    """Workflow status for community posts."""
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    NEEDS_CHANGES = "NEEDS_CHANGES"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


class Visibility(str, Enum):
    """Visibility settings for posts."""
    PUBLIC = "PUBLIC"
    BRANCH = "BRANCH"


class ReportReason(str, Enum):
    """Reason for reporting posts or comments."""
    SPAM = "SPAM"
    ABUSE = "ABUSE"
    HARASSMENT = "HARASSMENT"
    FALSE_INFORMATION = "FALSE_INFORMATION"
    FAKE_PROFILE = "FAKE_PROFILE"
    OTHER = "OTHER"


class ReportStatus(str, Enum):
    """Status workflow of spam/abuse reports."""
    PENDING = "PENDING"
    REVIEWED = "REVIEWED"
    DISMISSED = "DISMISSED"
