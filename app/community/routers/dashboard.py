"""
Moderation Dashboard Router.

Defines REST API endpoints for the operational Moderation Dashboard.
"""

import logging
from typing import Any
from fastapi import APIRouter, Depends, Query, Response

from app.community.schemas.dashboard import (
    DashboardSummary,
    DashboardStatisticsResponse,
    ModeratorActivityResponse,
    TrendAnalytics
)
from app.community.services.dashboard import ModerationDashboardService
from app.core.dependencies import (
    get_moderation_dashboard_service,
    require_roles,
    AuthenticatedUser,
    ADMIN,
    MODERATOR,
    SUPER_ADMIN
)
from app.core.responses import APIResponse, success_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/dashboard",
    response_model=APIResponse[DashboardSummary],
    summary="Dashboard Summary",
    description="Returns high-level summary of community posts.",
)
async def get_dashboard_summary(
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, SUPER_ADMIN])),
    dashboard_service: ModerationDashboardService = Depends(get_moderation_dashboard_service)
) -> Any:
    logger.info("REST Request - Dashboard Summary: user=%s", current_user.uid)
    summary = await dashboard_service.get_dashboard_summary(current_user.roles)
    
    return success_response(
        data=summary.model_dump(mode="json"),
        message="Dashboard summary fetched successfully."
    )


@router.get(
    "/statistics",
    response_model=APIResponse[DashboardStatisticsResponse],
    summary="Moderation Statistics",
    description="Returns detailed moderation statistics and analytics.",
)
async def get_dashboard_statistics(
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, SUPER_ADMIN])),
    dashboard_service: ModerationDashboardService = Depends(get_moderation_dashboard_service)
) -> Any:
    logger.info("REST Request - Dashboard Statistics: user=%s", current_user.uid)
    stats = await dashboard_service.get_dashboard_statistics(current_user.roles)
    
    return success_response(
        data=stats.model_dump(mode="json"),
        message="Moderation statistics fetched successfully."
    )


@router.get(
    "/activity",
    response_model=APIResponse[ModeratorActivityResponse],
    summary="Moderator Activity",
    description="Returns activity breakdown per moderator.",
)
async def get_moderator_activity(
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, SUPER_ADMIN, MODERATOR])),
    dashboard_service: ModerationDashboardService = Depends(get_moderation_dashboard_service)
) -> Any:
    logger.info("REST Request - Moderator Activity: user=%s", current_user.uid)
    activity = await dashboard_service.get_moderator_activity(current_user.roles, current_user.uid)
    
    return success_response(
        data=activity.model_dump(mode="json"),
        message="Moderator activity fetched successfully."
    )


@router.get(
    "/trends",
    response_model=APIResponse[TrendAnalytics],
    summary="Trend Analytics",
    description="Returns trend analytics for a specified period (daily, weekly, monthly).",
)
async def get_trend_analytics(
    period: str = Query("daily", description="Period for trends: daily, weekly, or monthly"),
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, SUPER_ADMIN])),
    dashboard_service: ModerationDashboardService = Depends(get_moderation_dashboard_service)
) -> Any:
    logger.info("REST Request - Trend Analytics: user=%s, period=%s", current_user.uid, period)
    trends = await dashboard_service.get_trend_analytics(current_user.roles, period)
    
    return success_response(
        data=trends.model_dump(mode="json"),
        message="Trend analytics fetched successfully."
    )


@router.get(
    "/export/summary",
    summary="Export Dashboard Summary CSV",
    description="Returns a CSV file containing dashboard summary metrics.",
)
async def export_dashboard_summary_csv(
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, SUPER_ADMIN])),
    dashboard_service: ModerationDashboardService = Depends(get_moderation_dashboard_service)
) -> Response:
    logger.info("REST Request - Export Dashboard Summary: user=%s", current_user.uid)
    csv_data = await dashboard_service.export_dashboard_summary_csv(current_user.roles)
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=dashboard_summary.csv"}
    )


@router.get(
    "/export/activity",
    summary="Export Moderator Activity CSV",
    description="Returns a CSV file containing moderator activity details.",
)
async def export_moderator_activity_csv(
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, SUPER_ADMIN, MODERATOR])),
    dashboard_service: ModerationDashboardService = Depends(get_moderation_dashboard_service)
) -> Response:
    logger.info("REST Request - Export Moderator Activity: user=%s", current_user.uid)
    csv_data = await dashboard_service.export_moderator_activity_csv(current_user.roles, current_user.uid)
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=moderator_activity.csv"}
    )
