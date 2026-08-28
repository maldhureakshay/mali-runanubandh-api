"""
Report domain model.

Defines the structure of a report document and includes recommended database indexes.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.community.enums import ReportReason, ReportStatus

# =====================================================================
# MongoDB Recommended Indexes for Reports Collection
# =====================================================================
# 1. Index on postId to retrieve all reports of a specific post:
#    db.reports.create_index([("postId", 1)])
#
# 2. Index on reportedBy to retrieve all reports submitted by a specific user:
#    db.reports.create_index([("reportedBy", 1)])
# =====================================================================


class Report(BaseModel):
    """
    Domain model representing a report filed against abusive/offensive community content.
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
    postId: str = Field(..., description="Target post ID that is reported")
    reportedBy: str = Field(..., description="User ID of the reporting user")
    reason: ReportReason = Field(..., description="Categorized reason for reporting")
    description: Optional[str] = Field(None, description="Detailed explanation/reason for report")
    status: ReportStatus = Field(default=ReportStatus.PENDING, description="The moderation status of the report")
    reviewedBy: Optional[str] = Field(None, description="Admin/moderator user ID who reviewed the report")
    reviewedAt: Optional[datetime] = Field(None, description="UTC timestamp when report was reviewed")
    createdAt: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of report creation")
