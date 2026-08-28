"""
Community Moderation Router.

Defines REST API endpoints for administrators and moderators to manage community reports,
approve or reject posts, and restore or delete posts.
"""

import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query, Response, status

from app.community.enums import PostType, ReportReason, ReportStatus
from app.community.schemas.report import ReportResponse, RejectPostRequest
from app.community.schemas.post import PostResponse
from app.community.schemas.moderation import (
    PendingPostSummaryResponse,
    ModerationPostDetailsResponse,
    ApprovePostRequest,
    NeedsChangesRequest,
    CreateMarriageAnnouncementRequest,
)
from app.community.schemas.review import PostReviewResponse
from app.community.services.report import ReportService
from app.community.services.review import PostReviewService
from app.community.services.moderation import ModerationService
from app.core.dependencies import (
    get_report_service,
    get_moderation_service,
    get_post_review_service,
    get_marriage_success_service,
    require_roles,
    AuthenticatedUser,
    ADMIN,
)
from app.community.routers.utils import enrich_posts_with_profile_snapshots
from app.core.responses import APIResponse, success_response

logger = logging.getLogger(__name__)

router = APIRouter()

# MODERATOR role string
MODERATOR = "MODERATOR"


@router.get(
    "/reports",
    response_model=APIResponse[List[ReportResponse]],
    summary="List all reports",
    description="Retrieves a paginated list of all abuse/spam reports submitted. Restricted to ADMIN and MODERATOR.",
)
async def list_reports(
    status_filter: Optional[ReportStatus] = Query(None, alias="status", description="Filter reports by status"),
    reason_filter: Optional[ReportReason] = Query(None, alias="reason", description="Filter reports by reason"),
    limit: int = Query(20, ge=1, le=100, description="Max number of items to return"),
    cursor: Optional[str] = Query(None, description="Cursor for next page pagination"),
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    report_service: ReportService = Depends(get_report_service)
) -> Any:
    logger.info("REST Request - List Reports: user=%s, status=%s, reason=%s", current_user.uid, status_filter, reason_filter)
    
    reports, next_cursor = await report_service.get_reports(
        status=status_filter.value if status_filter else None,
        reason=reason_filter.value if reason_filter else None,
        limit=limit,
        cursor=cursor
    )
    
    serialized_reports = [
        ReportResponse.model_validate(r.model_dump(by_alias=True)).model_dump(mode="json")
        for r in reports
    ]
    
    return success_response(
        data=serialized_reports,
        message="Reports fetched successfully.",
        status_code=status.HTTP_200_OK
    )


@router.get(
    "/reports/{reportId}",
    response_model=APIResponse[ReportResponse],
    summary="View report details",
    description="Fetches details of a specific report. Restricted to ADMIN and MODERATOR.",
)
async def get_report_details(
    reportId: str,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    report_service: ReportService = Depends(get_report_service)
) -> Any:
    logger.info("REST Request - Get Report Details: reportId=%s, user=%s", reportId, current_user.uid)
    
    report = await report_service.get_report_details(reportId)
    response_data = ReportResponse.model_validate(report.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Report details fetched successfully."
    )


@router.post(
    "/reports/{reportId}/dismiss",
    response_model=APIResponse[ReportResponse],
    summary="Dismiss report",
    description="Dismisses an abuse report, updating status to DISMISSED and decrementing post report counts. Restricted to ADMIN/MODERATOR.",
)
async def dismiss_report(
    reportId: str,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    report_service: ReportService = Depends(get_report_service)
) -> Any:
    logger.info("REST Request - Dismiss Report: reportId=%s, reviewer=%s", reportId, current_user.uid)
    
    report = await report_service.dismiss_report(report_id=reportId, reviewer_id=current_user.uid)
    response_data = ReportResponse.model_validate(report.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Report dismissed successfully."
    )


@router.post(
    "/reports/{reportId}/review",
    response_model=APIResponse[ReportResponse],
    summary="Mark report as reviewed",
    description="Marks an abuse report status as REVIEWED. Restricted to ADMIN and MODERATOR.",
)
async def review_report(
    reportId: str,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    report_service: ReportService = Depends(get_report_service)
) -> Any:
    logger.info("REST Request - Review Report: reportId=%s, reviewer=%s", reportId, current_user.uid)
    
    report = await report_service.review_report(report_id=reportId, reviewer_id=current_user.uid)
    response_data = ReportResponse.model_validate(report.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Report marked as reviewed successfully."
    )


@router.put(
    "/posts/{postId}/approve",
    response_model=APIResponse[PostResponse],
    summary="Approve a post",
    description="Approves a pending post, changing its status to APPROVED so it is visible in the public feed. Restricted to ADMIN/MODERATOR.",
)
async def approve_post(
    postId: str,
    payload: ApprovePostRequest,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    moderation_service: ModerationService = Depends(get_moderation_service)
) -> Any:
    logger.info("REST Request - Approve Post: postId=%s, reviewer=%s", postId, current_user.uid)
    
    post = await moderation_service.approve_post(
        post_id=postId, 
        admin_id=current_user.uid,
        approval_notes=payload.approvalNotes
    )
    response_data = PostResponse.model_validate(post.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Post approved successfully."
    )


@router.put(
    "/posts/{postId}/needs-changes",
    response_model=APIResponse[PostResponse],
    summary="Request changes on a post",
    description="Sends a pending post back to the author with required changes. Restricted to ADMIN/MODERATOR.",
)
async def request_changes(
    postId: str,
    payload: NeedsChangesRequest,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    moderation_service: ModerationService = Depends(get_moderation_service)
) -> Any:
    logger.info("REST Request - Request Changes: postId=%s, reviewer=%s", postId, current_user.uid)
    
    post = await moderation_service.request_changes(
        post_id=postId, 
        admin_id=current_user.uid,
        review_comments=payload.reviewComments,
        rejection_reason=payload.rejectionReason
    )
    response_data = PostResponse.model_validate(post.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Requested changes for post successfully."
    )


@router.post(
    "/posts/{postId}/reject",
    response_model=APIResponse[PostResponse],
    summary="Reject a post",
    description="Rejects a pending post, marking it as REJECTED with a moderation reason. Restricted to ADMIN/MODERATOR.",
)
async def reject_post(
    postId: str,
    payload: RejectPostRequest,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    moderation_service: ModerationService = Depends(get_moderation_service)
) -> Any:
    logger.info("REST Request - Reject Post: postId=%s, reviewer=%s, reason=%s", postId, current_user.uid, payload.reason)
    
    post = await moderation_service.reject_post(
        post_id=postId,
        admin_id=current_user.uid,
        reason=payload.reason
    )
    response_data = PostResponse.model_validate(post.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Post rejected successfully."
    )


@router.post(
    "/posts/{postId}/restore",
    response_model=APIResponse[PostResponse],
    summary="Restore a post",
    description="Restores a soft-deleted or rejected post, marking its status back to APPROVED. Restricted to ADMIN/MODERATOR.",
)
async def restore_post(
    postId: str,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    moderation_service: ModerationService = Depends(get_moderation_service)
) -> Any:
    logger.info("REST Request - Restore Post: postId=%s, reviewer=%s", postId, current_user.uid)
    
    post = await moderation_service.restore_post(post_id=postId, admin_id=current_user.uid)
    response_data = PostResponse.model_validate(post.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Post restored successfully."
    )


@router.post(
    "/posts/{postId}/delete",
    response_model=APIResponse[PostResponse],
    summary="Moderator delete post",
    description="Moderator-forced soft deletion of a post, marking its status as DELETED. Restricted to ADMIN/MODERATOR.",
)
async def delete_post(
    postId: str,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    moderation_service: ModerationService = Depends(get_moderation_service)
) -> Any:
    logger.info("REST Request - Moderator Delete Post: postId=%s, reviewer=%s", postId, current_user.uid)
    
    post = await moderation_service.delete_post(post_id=postId, admin_id=current_user.uid)
    response_data = PostResponse.model_validate(post.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Post soft-deleted by moderator successfully."
    )

@router.get(
    "/posts",
    response_model=APIResponse[List[PendingPostSummaryResponse]],
    summary="List pending posts",
    description="Retrieves a paginated list of submitted posts awaiting moderation review. Restricted to ADMIN and MODERATOR.",
)
async def list_pending_posts(
    type_filter: Optional[PostType] = Query(None, alias="type", description="Filter posts by type"),
    author_name: Optional[str] = Query(None, alias="authorName", description="Filter by author name"),
    author_id: Optional[str] = Query(None, alias="authorId", description="Filter by author ID"),
    submission_date: Optional[str] = Query(None, alias="submissionDate", description="Filter by submission date (YYYY-MM-DD)"),
    sort_order: int = Query(-1, description="Sort order: -1 for newest first, 1 for oldest first"),
    limit: int = Query(20, ge=1, le=100, description="Max number of items to return"),
    cursor: Optional[str] = Query(None, description="Cursor for next page pagination"),
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    moderation_service: ModerationService = Depends(get_moderation_service)
) -> Any:
    logger.info("REST Request - List Pending Posts: user=%s", current_user.uid)
    
    posts, next_cursor = await moderation_service.get_pending_posts(
        moderator_id=current_user.uid,
        post_type=type_filter,
        author_name=author_name,
        author_id=author_id,
        submission_date=submission_date,
        sort_order=sort_order,
        limit=limit,
        cursor=cursor
    )
    
    serialized_posts = [
        PendingPostSummaryResponse.model_validate(p.model_dump(by_alias=True)).model_dump(mode="json")
        for p in posts
    ]
    
    meta_data = {}
    if next_cursor:
        meta_data["next_cursor"] = next_cursor
    
    return success_response(
        data=serialized_posts,
        message="Pending posts fetched successfully.",
        status_code=status.HTTP_200_OK,
        meta=meta_data if meta_data else None
    )


@router.get(
    "/posts/managed",
    response_model=APIResponse[List[PostResponse]],
    summary="List managed posts by type",
    description=(
        "Retrieves a paginated list of posts of a given type for admin management. "
        "Supports filtering by announcementType, active/expired state, and created date. "
        "Restricted to ADMIN and MODERATOR."
    ),
)
async def list_managed_posts(
    type_filter: PostType = Query(..., alias="type", description="Post type to list (e.g. MARRIAGE_SUCCESS)"),
    announcement_type: Optional[str] = Query(None, alias="announcementType", description="Filter by announcementType (SINGLE_PERSON / COUPLE)"),
    active: Optional[bool] = Query(None, description="true = non-expired, false = expired, omit = all"),
    created_date: Optional[str] = Query(None, alias="createdDate", description="Filter by creation date (YYYY-MM-DD)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Comma-separated PostStatus values, e.g. APPROVED,ARCHIVED"),
    limit: int = Query(20, ge=1, le=100, description="Max number of items to return"),
    cursor: Optional[str] = Query(None, description="Cursor for next page pagination"),
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    moderation_service: ModerationService = Depends(get_moderation_service),
) -> Any:
    logger.info(
        "REST Request - List Managed Posts: type=%s, announcementType=%s, active=%s, date=%s, user=%s",
        type_filter, announcement_type, active, created_date, current_user.uid,
    )

    # Parse comma-separated status filter into a list of PostStatus, if provided
    from app.community.enums import PostStatus as PS
    parsed_statuses = None
    if status_filter:
        try:
            parsed_statuses = [PS(s.strip()) for s in status_filter.split(",") if s.strip()]
        except ValueError:
            from app.community.services.exceptions import ValidationException
            raise ValidationException(f"Invalid status value in filter: {status_filter}")

    posts, next_cursor = await moderation_service.get_admin_posts(
        admin_id=current_user.uid,
        post_type=type_filter,
        statuses=parsed_statuses,
        announcement_type=announcement_type,
        active=active,
        created_date=created_date,
        limit=limit,
        cursor=cursor,
    )

    serialized = [
        PostResponse.model_validate(p.model_dump(by_alias=True)).model_dump(mode="json")
        for p in posts
    ]

    meta_data = {}
    if next_cursor:
        meta_data["next_cursor"] = next_cursor

    return success_response(
        data=serialized,
        message="Managed posts fetched successfully.",
        status_code=status.HTTP_200_OK,
        meta=meta_data if meta_data else None,
    )


@router.get(
    "/posts/managed/{postId}",
    response_model=APIResponse[PostResponse],
    summary="View managed post details",
    description=(
        "Fetches full details of any post regardless of status for admin review. "
        "Unlike the moderation review endpoint, this works on APPROVED and ARCHIVED posts too. "
        "Restricted to ADMIN and MODERATOR."
    ),
)
async def get_managed_post_details(
    postId: str,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    moderation_service: ModerationService = Depends(get_moderation_service),
) -> Any:
    logger.info(
        "REST Request - Get Managed Post Details: postId=%s, user=%s", postId, current_user.uid
    )

    post = await moderation_service.get_post_details(post_id=postId, admin_id=current_user.uid)
    response_data = PostResponse.model_validate(post.model_dump(by_alias=True))

    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Managed post details fetched successfully.",
    )


@router.get(
    "/posts/{postId}",
    response_model=APIResponse[ModerationPostDetailsResponse],
    summary="View pending post details",
    description="Fetches full details of a pending post for moderation review. Restricted to ADMIN and MODERATOR.",
)
async def get_pending_post_details(
    postId: str,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN, MODERATOR])),
    moderation_service: ModerationService = Depends(get_moderation_service)
) -> Any:
    logger.info("REST Request - Get Pending Post Details: postId=%s, user=%s", postId, current_user.uid)
    
    post = await moderation_service.get_post_for_review(
        post_id=postId,
        moderator_id=current_user.uid
    )
    
    response_data = ModerationPostDetailsResponse.model_validate(post.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Pending post details fetched successfully."
    )


@router.get(
    "/posts/{postId}/history",
    response_model=APIResponse[List[PostReviewResponse]],
    summary="View post moderation history",
    description="Fetches the complete append-only review history of a post. Restricted to ADMIN, MODERATOR, and the post author.",
)
async def get_post_review_history(
    postId: str,
    sort_order: int = Query(1, description="Sort order: 1 for oldest first, -1 for newest first"),
    current_user: AuthenticatedUser = Depends(require_roles([])),
    review_service: PostReviewService = Depends(get_post_review_service)
) -> Any:
    logger.info("REST Request - Get Post Review History: postId=%s, user=%s", postId, current_user.uid)
    
    reviews = await review_service.get_review_history(
        post_id=postId,
        user_id=current_user.uid,
        user_roles=current_user.roles,
        sort_order=sort_order
    )
    
    response_data = [PostReviewResponse.model_validate(r.model_dump(by_alias=True)) for r in reviews]
    
    return success_response(
        data=[r.model_dump(mode="json") for r in response_data],
        message="Post review history fetched successfully."
    )


@router.post(
    "/marriage-announcements",
    response_model=APIResponse[PostResponse],
    summary="Create a marriage announcement",
    description=(
        "Admin-only endpoint to create and immediately publish a MARRIAGE_SUCCESS post. "
        "Validates that no active announcement already exists for the specified profile(s). "
        "Triggers a MARRIAGE_SUCCESS_CREATED event and notifies the profile owner(s). "
        "Restricted to ADMIN only."
    ),
    status_code=status.HTTP_201_CREATED,
)
async def create_marriage_announcement(
    payload: CreateMarriageAnnouncementRequest,
    current_user: AuthenticatedUser = Depends(require_roles([ADMIN])),
    marriage_service=Depends(get_marriage_success_service),
) -> Any:
    logger.info(
        "REST Request - Create Marriage Announcement: admin=%s, type=%s, person1=%s, person2=%s",
        current_user.uid,
        payload.announcementType,
        payload.person1ProfileId,
        payload.person2ProfileId,
    )

    from app.community.models.post import AuthorSnapshot, Content, VisibilitySettings
    from app.community.enums import Visibility

    admin_author = AuthorSnapshot(
        userId=current_user.uid,
        profileId=current_user.uid,
        fullName=current_user.name or "Admin",
        verified=True,
        paidMember=True,
    )

    post = await marriage_service.create_marriage_announcement(
        admin_id=current_user.uid,
        admin_author=admin_author,
        announcement_type=payload.announcementType,
        person1_profile_id=payload.person1ProfileId,
        content=payload.content,
        person2_profile_id=payload.person2ProfileId,
        visibility=payload.visibility or Visibility.PUBLIC,
    )

    response_data = PostResponse.model_validate(post.model_dump(by_alias=True))
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Marriage announcement created and published successfully.",
        status_code=status.HTTP_201_CREATED,
    )
