"""
NotificationHandler implementation.

Subscribes to domain events and creates corresponding user notifications.
"""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.events.base_event import BaseEvent
from app.events.event_types import EventType
from app.events.handler import EventHandler
from app.notifications.services.notification import NotificationService

logger = logging.getLogger(__name__)


class NotificationHandler(EventHandler):
    """
    Subscribes to platform events and uses NotificationService to notify users.
    """

    def __init__(self, notification_service: NotificationService, db: AsyncIOMotorDatabase) -> None:
        """
        Initialize the handler with the notification service and MongoDB client.
        """
        self._notification_service = notification_service
        self._db = db

    async def handle(self, event: BaseEvent) -> None:
        """
        Handle incoming events and generate user notifications.
        """
        event_type = event.eventType
        payload = event.payload

        logger.info("NotificationHandler processing event: type=%s, id=%s", event_type, event.eventId)

        try:
            if event_type == EventType.POST_APPROVED:
                await self._handle_post_approved(payload)
            elif event_type == EventType.POST_REJECTED:
                await self._handle_post_rejected(payload)
            elif event_type == EventType.COMMENT_CREATED:
                await self._handle_comment_created(payload)
            elif event_type == EventType.POST_LIKED:
                await self._handle_post_liked(payload)
            elif event_type == EventType.ANNOUNCEMENT_PUBLISHED:
                await self._handle_announcement_published(payload)
            elif event_type == EventType.MARRIAGE_SUCCESS_CREATED:
                await self._handle_marriage_success_created(payload)
            elif event_type == EventType.POLL_VOTED:
                # Keep implementation ready for future voting notifications
                logger.info("NotificationHandler: POLL_VOTED event received. Keeping ready for future integration.")
            elif event_type == EventType.BIRTHDAY_WISH_CREATED:
                await self._handle_birthday_wish_created(payload)
            else:
                logger.debug("NotificationHandler: Ignored unmapped event type: %s", event_type)
        except Exception as e:
            logger.error("Failed to generate notification for event %s: %s", event.eventId, e, exc_info=True)

    async def _handle_birthday_wish_created(self, payload: dict) -> None:
        post_id = payload.get("postId")
        birthday_profile_id = payload.get("birthdayProfileId")
        commenter_user_id = payload.get("commenterUserId")
        comment_id = payload.get("commentId")

        if not post_id or not birthday_profile_id or not commenter_user_id or not comment_id:
            logger.warning("Notification rejected: Missing required fields in payload.")
            return

        # 1. Fetch post to verify type and status and expiration
        from bson import ObjectId
        query = {"_id": post_id}
        if ObjectId.is_valid(post_id):
            query = {"_id": ObjectId(post_id)}
        post_doc = await self._db.posts.find_one(query)
        if not post_doc:
            logger.warning("Notification rejected: post %s not found.", post_id)
            return

        if post_doc.get("type") != "BIRTHDAY":
            logger.warning("Notification rejected: post %s is not a BIRTHDAY post.", post_id)
            return

        if post_doc.get("moderation", {}).get("status") != "APPROVED":
            logger.warning("Notification rejected: post %s status is not APPROVED.", post_id)
            return

        import datetime
        from datetime import timezone
        expires_at = post_doc.get("expiresAt")
        if expires_at:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.datetime.now(timezone.utc):
                logger.warning("Notification rejected: birthday post %s has expired.", post_id)
                return

        # 2. Verify recipient profile exists and map profileId to userId
        query_recipient = {"_id": birthday_profile_id}
        if ObjectId.is_valid(birthday_profile_id):
            query_recipient = {"_id": ObjectId(birthday_profile_id)}
        profile_doc = await self._db.profiles.find_one(query_recipient)
        if not profile_doc:
            logger.warning("Notification rejected: birthday recipient profile %s not found.", birthday_profile_id)
            return

        recipient_user_id = profile_doc.get("userId")
        if not recipient_user_id:
            logger.warning("Notification rejected: birthday recipient profile %s has no userId.", birthday_profile_id)
            return

        # Ensure commenter is not the birthday person
        if commenter_user_id == recipient_user_id:
            logger.warning("Notification rejected: commenter is the birthday recipient themselves.")
            return

        # Get commenter name
        commenter_doc = await self._db.profiles.find_one({"userId": commenter_user_id})
        commenter_name = commenter_doc.get("full_name") if commenter_doc else "Someone"
        if not commenter_name:
            commenter_name = "Someone"

        await self._notification_service.create_notification(
            recipient_user_id=recipient_user_id,
            actor_user_id=commenter_user_id,
            notification_type="BIRTHDAY_WISH",
            title="Happy Birthday!",
            message=f"{commenter_name} wished you a Happy Birthday! 🎂",
            reference_type="COMMENT",
            reference_id=comment_id
        )

    async def _handle_post_approved(self, payload: dict) -> None:
        author_id = payload.get("authorId") or payload.get("author", {}).get("userId")
        post_id = payload.get("postId") or payload.get("id")
        if not author_id or not post_id:
            return

        await self._notification_service.create_notification(
            recipient_user_id=author_id,
            actor_user_id=None,
            notification_type="POST_APPROVED",
            title="Post Approved",
            message="Your community post has been approved by moderation.",
            reference_type="POST",
            reference_id=post_id
        )

    async def _handle_post_rejected(self, payload: dict) -> None:
        author_id = payload.get("authorId") or payload.get("author", {}).get("userId")
        post_id = payload.get("postId") or payload.get("id")
        reason = payload.get("rejectionReason") or payload.get("moderation", {}).get("rejectionReason") or "Policy violation"
        if not author_id or not post_id:
            return

        await self._notification_service.create_notification(
            recipient_user_id=author_id,
            actor_user_id=None,
            notification_type="POST_REJECTED",
            title="Post Rejected",
            message=f"Your post was rejected. Reason: {reason}",
            reference_type="POST",
            reference_id=post_id
        )

    async def _handle_comment_created(self, payload: dict) -> None:
        post_id = payload.get("postId")
        actor_id = payload.get("author", {}).get("userId")
        comment_id = payload.get("id")
        comment_text = payload.get("comment", "")
        if not post_id or not actor_id:
            return

        # Fetch post to find the owner
        post_doc = await self._db.posts.find_one({"_id": post_id})
        if not post_doc:
            # Fallback if query returns none or ObjectId conversion is needed
            from bson import ObjectId
            if ObjectId.is_valid(post_id):
                post_doc = await self._db.posts.find_one({"_id": ObjectId(post_id)})

        if not post_doc:
            logger.warning("Could not find post %s to notify owner of comment.", post_id)
            return

        # Extract post owner
        post_owner_id = post_doc.get("author", {}).get("userId")
        if not post_owner_id:
            return

        # Do not notify if commenting on own post
        if post_owner_id == actor_id:
            logger.debug("Skipping notification: Comment author is the post owner.")
            return

        truncated_text = comment_text[:50] + "..." if len(comment_text) > 50 else comment_text
        await self._notification_service.create_notification(
            recipient_user_id=post_owner_id,
            actor_user_id=actor_id,
            notification_type="COMMENT_ADDED",
            title="New Comment",
            message=f"Someone commented on your post: \"{truncated_text}\"",
            reference_type="COMMENT",
            reference_id=comment_id
        )

    async def _handle_post_liked(self, payload: dict) -> None:
        post_id = payload.get("postId")
        actor_id = payload.get("userId")
        if not post_id or not actor_id:
            return

        # Find post owner
        from bson import ObjectId
        query = {"_id": post_id}
        if ObjectId.is_valid(post_id):
            query = {"_id": ObjectId(post_id)}
        post_doc = await self._db.posts.find_one(query)

        if not post_doc:
            logger.warning("Could not find post %s to notify owner of like.", post_id)
            return

        post_owner_id = post_doc.get("author", {}).get("userId")
        if not post_owner_id:
            return

        # Do not notify self-likes
        if post_owner_id == actor_id:
            return

        await self._notification_service.create_notification(
            recipient_user_id=post_owner_id,
            actor_user_id=actor_id,
            notification_type="POST_LIKED",
            title="Post Liked",
            message="Someone liked your post.",
            reference_type="POST",
            reference_id=post_id
        )

    async def _handle_announcement_published(self, payload: dict) -> None:
        post_id = payload.get("id")
        title = payload.get("content", {}).get("title") or "Important Announcement"
        
        # Design this to support future background processing scale
        logger.info("Broadcasting announcement %s to all active users...", post_id)
        
        # Fetch all distinct user IDs from profiles collection
        try:
            user_ids = await self._db.profiles.distinct("userId")
            if not user_ids:
                logger.warning("No users found in profiles collection for announcement broadcast.")
                return

            for uid in user_ids:
                if not uid:
                    continue
                # Create notification asynchronously per user
                await self._notification_service.create_notification(
                    recipient_user_id=uid,
                    actor_user_id=None,
                    notification_type="ANNOUNCEMENT",
                    title="Announcement",
                    message=title,
                    reference_type="POST",
                    reference_id=post_id
                )
            logger.info("Successfully broadcasted announcement %s to %d users.", post_id, len(user_ids))
        except Exception as e:
            logger.error("Failed to broadcast announcement: %s", e)

    async def _handle_marriage_success_created(self, payload: dict) -> None:
        """
        Notify the profiled person(s) that their marriage announcement has been
        published to the community.

        Payload fields:
          - postId: str
          - person1ProfileId: str
          - person2ProfileId: str | None
          - createdByAdminId: str
        """
        post_id = payload.get("postId")
        person1_profile_id = payload.get("person1ProfileId")
        person2_profile_id = payload.get("person2ProfileId")

        if not post_id or not person1_profile_id:
            logger.warning(
                "MARRIAGE_SUCCESS_CREATED notification skipped: missing postId or person1ProfileId."
            )
            return

        MARRIAGE_NOTIFICATION_MESSAGE = (
            "Your marriage announcement has been shared with the community! 🎉"
        )
        MARRIAGE_NOTIFICATION_TITLE = "Marriage Announcement"

        async def _notify_profile(profile_id: str) -> None:
            """Resolve profileId → userId and send notification. Skips on not found."""
            from bson import ObjectId
            query = (
                {"_id": ObjectId(profile_id)}
                if ObjectId.is_valid(profile_id)
                else {"_id": profile_id}
            )
            profile_doc = await self._db.profiles.find_one(query)
            if not profile_doc:
                logger.warning(
                    "MARRIAGE_SUCCESS_CREATED notification skipped: profile %s not found.",
                    profile_id,
                )
                return

            recipient_user_id = profile_doc.get("userId")
            if not recipient_user_id:
                logger.warning(
                    "MARRIAGE_SUCCESS_CREATED notification skipped: profile %s has no userId.",
                    profile_id,
                )
                return

            await self._notification_service.create_notification(
                recipient_user_id=recipient_user_id,
                actor_user_id=None,
                notification_type="MARRIAGE_ANNOUNCEMENT",
                title=MARRIAGE_NOTIFICATION_TITLE,
                message=MARRIAGE_NOTIFICATION_MESSAGE,
                reference_type="POST",
                reference_id=post_id,
            )
            logger.info(
                "Marriage announcement notification sent to userId=%s (profileId=%s) for post %s.",
                recipient_user_id,
                profile_id,
                post_id,
            )

        # Notify person 1 (always present)
        await _notify_profile(person1_profile_id)

        # Notify person 2 if COUPLE announcement
        if person2_profile_id:
            await _notify_profile(person2_profile_id)
