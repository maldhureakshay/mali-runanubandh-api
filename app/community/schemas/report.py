"""
Report Schemas module.

Defines Pydantic request and response schemas for validating post/comment abuse reports.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.community.enums import ReportReason, ReportStatus


class ReportCreate(BaseModel):
    """
    Request payload schema to report content.
    """
    reason: ReportReason = Field(..., description="Categorized abuse report reason")
    description: Optional[str] = Field(None, max_length=500, description="Additional context details")


class ReportResponse(BaseModel):
    """
    API Response schema returning report submission status.
    """
    id: str = Field(..., alias="_id", description="MongoDB report ID")
    postId: str = Field(..., description="Target post ID which was reported")
    reportedBy: str = Field(..., description="User ID of the reporter")
    reason: ReportReason = Field(..., description="Report category")
    description: Optional[str] = Field(None, description="Context details")
    status: ReportStatus = Field(..., description="Workflow status of the report")
    reviewedBy: Optional[str] = Field(None, description="Moderator user ID who reviewed the report")
    reviewedAt: Optional[datetime] = Field(None, description="UTC timestamp of the review")
    createdAt: datetime = Field(..., description="UTC creation timestamp")

    model_config = {
        "populate_by_name": True
    }


class RejectPostRequest(BaseModel):
    """
    Request payload schema for rejecting a community post.
    """
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for rejection")
