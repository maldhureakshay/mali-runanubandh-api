"""
Notification Repository module.

Handles MongoDB operations for the notifications collection.
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional, Tuple

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.notifications.models.notification import Notification
from app.community.repositories.base import BaseRepository
from app.community.repositories.exceptions import DocumentNotFoundException, RepositoryException

logger = logging.getLogger(__name__)


class NotificationRepository(BaseRepository):
    """
    Handles database operations for notifications.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """
        Initializes the repository with the notifications collection name.
        """
        super().__init__(db, "notifications")

    async def create_notification(self, notification: Notification) -> Notification:
        """
        Insert a new notification document.
        """
        notification_data = notification.model_dump(by_alias=True, exclude={"id"})
        if notification.id:
            notification_data["_id"] = ObjectId(notification.id)
            
        created = await self.create(notification_data)
        return Notification.model_validate(created)

    async def get_notification(self, notification_id: str) -> Notification:
        """
        Fetch a single notification by ID.
        """
        doc = await self.find_by_id(notification_id)
        return Notification.model_validate(doc)

    async def find_by_recipient(
        self,
        recipient_user_id: str,
        read_filter: Optional[bool] = None,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> Tuple[List[Notification], Optional[str]]:
        """
        Retrieve notifications for a recipient, sorted newest first (createdAt descending).
        """
        filters = {"recipientUserId": recipient_user_id}
        if read_filter is not None:
            filters["read"] = read_filter
            
        # Ordered newest first
        sort = [("createdAt", -1), ("_id", -1)]
        
        docs, next_cursor = await self.find_many(filters, sort=sort, limit=limit, cursor=cursor)
        notifications = [Notification.model_validate(doc) for doc in docs]
        return notifications, next_cursor

    async def mark_as_read(self, notification_id: str) -> Notification:
        """
        Mark a specific notification as read.
        """
        if not ObjectId.is_valid(notification_id):
            raise DocumentNotFoundException(f"Invalid notification ID: {notification_id}")
            
        current_time = datetime.now(timezone.utc)
        try:
            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(notification_id)},
                {
                    "$set": {
                        "read": True,
                        "readAt": current_time
                    }
                },
                return_document=True
            )
            if not result:
                raise DocumentNotFoundException(f"Notification {notification_id} not found.")
            return Notification.model_validate(result)
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error marking notification %s as read: %s", notification_id, e)
            raise RepositoryException(message=f"Database update error: {e}")

    async def mark_all_as_read(self, recipient_user_id: str) -> int:
        """
        Mark all unread notifications for a user as read. Returns the count of updated notifications.
        """
        current_time = datetime.now(timezone.utc)
        try:
            result = await self.collection.update_many(
                {
                    "recipientUserId": recipient_user_id,
                    "read": False
                },
                {
                    "$set": {
                        "read": True,
                        "readAt": current_time
                    }
                }
            )
            return result.modified_count
        except Exception as e:
            logger.error("Error marking all notifications read for user %s: %s", recipient_user_id, e)
            raise RepositoryException(message=f"Database update error: {e}")

    async def get_unread_count(self, recipient_user_id: str) -> int:
        """
        Return count of unread notifications for a recipient.
        """
        return await self.count({
            "recipientUserId": recipient_user_id,
            "read": False
        })
