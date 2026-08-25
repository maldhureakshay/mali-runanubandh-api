"""
Dashboard Schemas module.

Defines Pydantic schemas for the Moderation Dashboard endpoints.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    pendingReviewCount: int = Field(0, description="Number of posts currently in PENDING_REVIEW")
    approvedToday: int = Field(0, description="Posts approved today (UTC)")
    approvedThisWeek: int = Field(0, description="Posts approved this week")
    approvedThisMonth: int = Field(0, description="Posts approved this month")
    needsChangesCount: int = Field(0, description="Posts currently in NEEDS_CHANGES")
    draftCount: int = Field(0, description="Posts currently in DRAFT")
    archivedCount: int = Field(0, description="Posts currently ARCHIVED")
    deletedCount: int = Field(0, description="Posts currently DELETED")
    totalCommunityPosts: int = Field(0, description="Total number of community posts (excluding deleted)")


class ModerationMetrics(BaseModel):
    totalReviews: int = Field(0, description="Total number of moderation actions taken")
    approvalRate: float = Field(0.0, description="Percentage of reviews that resulted in approval")
    needsChangesRate: float = Field(0.0, description="Percentage of reviews that requested changes")
    averageReviewTimeMinutes: float = Field(0.0, description="Average time in minutes a post spends pending review")
    averageResubmissionTimeMinutes: float = Field(0.0, description="Average time in minutes an author takes to resubmit")
    totalPending: int = Field(0, description="Total currently pending posts")
    oldestPendingPostDate: Optional[str] = Field(None, description="ISO timestamp of the oldest pending post")
    newestPendingPostDate: Optional[str] = Field(None, description="ISO timestamp of the newest pending post")


class PostAnalytics(BaseModel):
    byType: Dict[str, int] = Field(default_factory=dict, description="Count of posts grouped by type (DISCUSSION, POLL, etc.)")
    byStatus: Dict[str, int] = Field(default_factory=dict, description="Count of posts grouped by status")


class ModeratorActivityItem(BaseModel):
    moderatorId: str
    moderatorName: Optional[str] = None
    totalReviews: int = 0
    approvals: int = 0
    needsChanges: int = 0
    averageReviewTimeMinutes: float = 0.0
    reviewsToday: int = 0
    reviewsThisWeek: int = 0
    lastReviewTime: Optional[str] = None


class ModeratorActivityResponse(BaseModel):
    activity: List[ModeratorActivityItem]


class TrendDataPoint(BaseModel):
    date: str = Field(..., description="Date key (e.g. 'YYYY-MM-DD', 'YYYY-MM')")
    submittedPosts: int = 0
    approvedPosts: int = 0
    needsChanges: int = 0
    resubmissions: int = 0
    archivedPosts: int = 0


class TrendAnalytics(BaseModel):
    period: str = Field(..., description="daily, weekly, or monthly")
    trends: List[TrendDataPoint]


class DashboardStatisticsResponse(BaseModel):
    summary: DashboardSummary
    metrics: ModerationMetrics
    postAnalytics: PostAnalytics
