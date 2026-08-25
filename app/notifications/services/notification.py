"""
Notification Service module.

Implements business logic for creating, retrieving, and updating user notifications.
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional, Tuple

from app.notifications.models.notification import Notification
from app.notifications.repositories.notification import NotificationRepository
from app.community.repositories.exceptions import DocumentNotFoundException
from app.core.exceptions import ForbiddenException, NotFoundException

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Handles business services for User Notifications.
    """

    def __init__(self, notification_repo: NotificationRepository) -> None:
        """
        Dependency injects NotificationRepository.
        """
        self.notification_repo = notification_repo

    async def create_notification(
        self,
        recipient_user_id: str,
        actor_user_id: Optional[str],
        notification_type: str,
        title: str,
        message: str,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None
    ) -> Notification:
        """
        Create a new notification for a user.
        """
        notification = Notification(
            recipientUserId=recipient_user_id,
            actorUserId=actor_user_id,
            type=notification_type,
            title=title,
            message=message,
            referenceType=reference_type,
            referenceId=reference_id,
            read=False,
            createdAt=datetime.now(timezone.utc)
        )
        created = await self.notification_repo.create_notification(notification)
        logger.info("Notification Created: ID %s for user %s type %s", created.id, recipient_user_id, notification_type)
        return created

    async def get_user_notifications(
        self,
        recipient_user_id: str,
        read_filter: Optional[bool] = None,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> Tuple[List[Notification], Optional[str]]:
        """
        Retrieve paginated notifications for the specified recipient.
        """
        return await self.notification_repo.find_by_recipient(
            recipient_user_id=recipient_user_id,
            read_filter=read_filter,
            limit=limit,
            cursor=cursor
        )

    async def get_unread_count(self, recipient_user_id: str) -> int:
        """
        Return the count of unread notifications for a user.
        """
        return await self.notification_repo.get_unread_count(recipient_user_id)

    async def mark_as_read(self, notification_id: str, recipient_user_id: str) -> Notification:
        """
        Mark a notification as read, validating ownership.
        """
        try:
            notification = await self.notification_repo.get_notification(notification_id)
        except DocumentNotFoundException:
            raise NotFoundException(message="Notification not found.")

        # Enforce Ownership: Users can only mark their own notifications as read
        if notification.recipientUserId != recipient_user_id:
            logger.warning(
                "Authorization failure: User %s attempted to read notification %s owned by %s.",
                recipient_user_id,
                notification_id,
                notification.recipientUserId
            )
            raise ForbiddenException(message="You do not have permission to access this notification.")

        updated = await self.notification_repo.mark_as_read(notification_id)
        logger.info("Notification Read: ID %s read by user %s", notification_id, recipient_user_id)
        return updated

    async def mark_all_as_read(self, recipient_user_id: str) -> int:
        """
        Mark all unread notifications for a user as read.
        """
        count = await self.notification_repo.mark_all_as_read(recipient_user_id)
        logger.info("Notifications Read: Marked all (%d) read for user %s", count, recipient_user_id)
        return count

    async def delete_notification(self, notification_id: str, recipient_user_id: str) -> bool:
        """
        Delete a notification, validating ownership.
        """
        try:
            notification = await self.notification_repo.get_notification(notification_id)
        except DocumentNotFoundException:
            raise NotFoundException(message="Notification not found.")

        # Enforce Ownership: Users can only delete their own notifications
        if notification.recipientUserId != recipient_user_id:
            logger.warning(
                "Authorization failure: User %s attempted to delete notification %s owned by %s.",
                recipient_user_id,
                notification_id,
                notification.recipientUserId
            )
            raise ForbiddenException(message="You do not have permission to delete this notification.")

        success = await self.notification_repo.delete(notification_id)
        logger.info("Notification Deleted: ID %s deleted by user %s", notification_id, recipient_user_id)
        return success
