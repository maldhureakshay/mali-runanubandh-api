"""
Notifications API Router.

Defines REST API endpoints for user notifications. Handles response formatting and validation.
"""

import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query, Response, status

from app.notifications.schemas.notification import NotificationResponse, UnreadCountResponse
from app.notifications.services.notification import NotificationService
from app.core.dependencies import get_current_user, get_notification_service, AuthenticatedUser
from app.core.responses import APIResponse, success_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=APIResponse[List[NotificationResponse]],
    summary="Get user notifications",
    description="Retrieves a list of notifications for the authenticated user, sorted newest first, with cursor pagination.",
)
async def get_notifications(
    read: Optional[bool] = Query(None, description="Filter by read/unread status"),
    limit: int = Query(20, ge=1, le=100, description="Max number of items to return"),
    cursor: Optional[str] = Query(None, description="Cursor for next page pagination"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
) -> Any:
    logger.info("REST Request - Get Notifications: user=%s, limit=%d", current_user.uid, limit)
    
    notifications, next_cursor = await notification_service.get_user_notifications(
        recipient_user_id=current_user.uid,
        read_filter=read,
        limit=limit,
        cursor=cursor
    )
    
    serialized = [
        NotificationResponse.model_validate(n.model_dump(by_alias=True)).model_dump(mode="json")
        for n in notifications
    ]
    
    return success_response(
        data=serialized,
        message="Notifications fetched successfully.",
        status_code=status.HTTP_200_OK
    )


@router.get(
    "/unread-count",
    response_model=APIResponse[UnreadCountResponse],
    summary="Get unread notifications count",
    description="Returns the total number of unread notifications for the authenticated user.",
)
async def get_unread_count(
    current_user: AuthenticatedUser = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
) -> Any:
    logger.info("REST Request - Get Unread Count: user=%s", current_user.uid)
    
    count = await notification_service.get_unread_count(current_user.uid)
    
    return success_response(
        data=UnreadCountResponse(unreadCount=count).model_dump(mode="json"),
        message="Unread notification count fetched successfully."
    )


@router.put(
    "/{notificationId}/read",
    response_model=APIResponse[NotificationResponse],
    summary="Mark notification as read",
    description="Marks a specific notification as read. The notification must belong to the authenticated user.",
)
async def mark_as_read(
    notificationId: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
) -> Any:
    logger.info("REST Request - Mark Read: notificationId=%s, user=%s", notificationId, current_user.uid)
    
    notification = await notification_service.mark_as_read(notificationId, current_user.uid)
    response_data = NotificationResponse.model_validate(notification.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Notification marked as read successfully."
    )


@router.put(
    "/read-all",
    response_model=APIResponse[dict],
    summary="Mark all notifications as read",
    description="Marks all unread notifications belonging to the authenticated user as read.",
)
async def mark_all_as_read(
    current_user: AuthenticatedUser = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
) -> Any:
    logger.info("REST Request - Mark All Read: user=%s", current_user.uid)
    
    count = await notification_service.mark_all_as_read(current_user.uid)
    
    return success_response(
        data={"markedReadCount": count},
        message="All notifications marked as read successfully."
    )


@router.delete(
    "/{notificationId}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Delete a notification",
    description="Permanently deletes a notification document. The notification must belong to the authenticated user.",
)
async def delete_notification(
    notificationId: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
) -> Any:
    logger.info("REST Request - Delete Notification: notificationId=%s, user=%s", notificationId, current_user.uid)
    
    await notification_service.delete_notification(notificationId, current_user.uid)
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)
