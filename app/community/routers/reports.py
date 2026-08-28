"""
Community Reports Router.

Defines REST API endpoints for users to report inappropriate posts,
and for moderators to list reports for a specific post.
"""

import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query, status

from app.community.enums import ReportReason, ReportStatus
from app.community.schemas.report import ReportCreate, ReportResponse
from app.community.services.report import ReportService
from app.core.dependencies import (
    get_report_service,
    get_current_user,
    require_roles,
    AuthenticatedUser,
    ADMIN,
)
from app.core.responses import APIResponse, success_response

logger = logging.getLogger(__name__)

router = APIRouter()

# MODERATOR is also permitted (ADMIN role is already defined)
MODERATOR = "MODERATOR"


@router.post(
    "/report",
    response_model=APIResponse[ReportResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Report a post",
    description="Submits an abuse/spam report against a community post. Users cannot report their own post or report a post twice.",
)
async def report_post(
    postId: str,
    payload: ReportCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
) -> Any:
    logger.info("REST Request - Report Post: postId=%s, user=%s", postId, current_user.uid)
    
    report = await report_service.report_post(
        post_id=postId,
        reported_by=current_user.uid,
        reason=payload.reason,
        description=payload.description
    )
    
    response_data = ReportResponse.model_validate(report.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Post reported successfully.",
        status_code=status.HTTP_201_CREATED
    )


@router.get(
    "/reports",
    response_model=APIResponse[List[ReportResponse]],
    summary="Get reports for a specific post",
    description="Retrieves a list of reports submitted against the specified post. Restricted to ADMIN and MODERATOR roles.",
)
async def get_post_reports(
    postId: str,
    status_filter: Optional[ReportStatus] = Query(None, alias="status", description="Filter reports by status"),
    reason_filter: Optional[ReportReason] = Query(None, alias="reason", description="Filter reports by reason"),
    limit: int = Query(20, ge=1, le=100, description="Max number of items to return"),
    cursor: Optional[str] = Query(None, description="Cursor for next page pagination"),
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    report_service: ReportService = Depends(get_report_service)
) -> Any:
    logger.info("REST Request - Get Post Reports: postId=%s, user=%s", postId, current_user.uid)
    
    # We query reports filtered by postId
    reports, next_cursor = await report_service.report_repo.find_reports(
        status=status_filter.value if status_filter else None,
        reason=reason_filter.value if reason_filter else None,
        limit=limit,
        cursor=cursor
    )
    
    # Filter reports belonging to the current postId
    filtered_reports = [r for r in reports if r.postId == postId]
    
    serialized_reports = [
        ReportResponse.model_validate(r.model_dump(by_alias=True)).model_dump(mode="json")
        for r in filtered_reports
    ]
    
    return success_response(
        data=serialized_reports,
        message="Reports fetched successfully.",
        status_code=status.HTTP_200_OK
    )
