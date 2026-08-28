"""
Moderation Dashboard Service module.

Coordinates data aggregation and business logic for the moderation dashboard.
"""

import csv
import io
import logging
from typing import Any, Dict, List

from app.community.repositories.dashboard import ModerationDashboardRepository
from app.community.schemas.dashboard import (
    DashboardStatisticsResponse,
    DashboardSummary,
    ModerationMetrics,
    PostAnalytics,
    ModeratorActivityResponse,
    ModeratorActivityItem,
    TrendAnalytics
)
from app.core.exceptions import ForbiddenException

logger = logging.getLogger(__name__)


class ModerationDashboardService:
    """
    Service handling operational dashboards and exports.
    """

    def __init__(self, dashboard_repo: ModerationDashboardRepository) -> None:
        self.dashboard_repo = dashboard_repo

    def _verify_admin_access(self, user_roles: List[str]) -> None:
        """
        Verify that the user has ADMIN or SUPER_ADMIN access.
        """
        if not any(role in ["ADMIN", "SUPER_ADMIN"] for role in user_roles):
            raise ForbiddenException("Access denied. Only administrators can view dashboard statistics.")

    async def get_dashboard_summary(self, user_roles: List[str]) -> DashboardSummary:
        """
        Get high-level summary of community posts.
        """
        self._verify_admin_access(user_roles)
        stats = await self.dashboard_repo.aggregate_summary_stats()
        return DashboardSummary.model_validate(stats)

    async def get_dashboard_statistics(self, user_roles: List[str], trend_period: str = "daily") -> DashboardStatisticsResponse:
        """
        Get detailed moderation metrics and post analytics.
        """
        self._verify_admin_access(user_roles)
        
        summary_stats = await self.dashboard_repo.aggregate_summary_stats()
        metrics_stats = await self.dashboard_repo.aggregate_moderation_metrics()
        analytics_stats = await self.dashboard_repo.aggregate_post_analytics()
        
        summary = DashboardSummary.model_validate(summary_stats)
        metrics = ModerationMetrics.model_validate(metrics_stats)
        analytics = PostAnalytics.model_validate(analytics_stats)
        
        # We can also add trend analytics but it's not strictly part of DashboardStatisticsResponse
        # However, the user might want it separate or together. For now it's returned here or as separate.
        
        return DashboardStatisticsResponse(
            summary=summary,
            metrics=metrics,
            postAnalytics=analytics
        )
        
    async def get_trend_analytics(self, user_roles: List[str], period: str = "daily") -> TrendAnalytics:
        self._verify_admin_access(user_roles)
        trends = await self.dashboard_repo.aggregate_trend_analytics(period)
        return TrendAnalytics(period=period, trends=trends)

    async def get_moderator_activity(
        self, 
        user_roles: List[str], 
        user_id: str
    ) -> ModeratorActivityResponse:
        """
        Get activity breakdown per moderator.
        Moderators can only see their own activity, Admins can see all.
        """
        is_admin = any(role in ["ADMIN", "SUPER_ADMIN"] for role in user_roles)
        is_moderator = "MODERATOR" in user_roles
        
        if not is_admin and not is_moderator:
            raise ForbiddenException("Access denied. Only administrators and moderators can view activity.")
            
        activity_data = await self.dashboard_repo.aggregate_moderator_activity()
        
        if not is_admin:
            # Moderators can only see themselves
            activity_data = [item for item in activity_data if item["moderatorId"] == user_id]
            
        items = [ModeratorActivityItem.model_validate(item) for item in activity_data]
        return ModeratorActivityResponse(activity=items)
        
    async def export_dashboard_summary_csv(self, user_roles: List[str]) -> str:
        """
        Generate CSV export for dashboard summary.
        """
        self._verify_admin_access(user_roles)
        stats = await self.dashboard_repo.aggregate_summary_stats()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Metric", "Count"])
        for key, value in stats.items():
            writer.writerow([key, value])
            
        return output.getvalue()
        
    async def export_moderator_activity_csv(self, user_roles: List[str], user_id: str) -> str:
        """
        Generate CSV export for moderator activity.
        """
        activity_res = await self.get_moderator_activity(user_roles, user_id)
        
        output = io.StringIO()
        writer = csv.writer(output)
        if not activity_res.activity:
            writer.writerow(["No data"])
            return output.getvalue()
            
        # Headers
        headers = list(activity_res.activity[0].model_dump().keys())
        writer.writerow(headers)
        
        for item in activity_res.activity:
            row = [getattr(item, h) for h in headers]
            writer.writerow(row)
            
        return output.getvalue()
