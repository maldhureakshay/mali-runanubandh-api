"""
Marriage Success Service module.

Implements admin-only business logic for creating and managing MARRIAGE_SUCCESS
community posts. Reuses PostRepository, EventPublisher, and existing Post domain model.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.community.enums import PostStatus, PostType, Visibility
from app.community.models.post import (
    AuthorSnapshot,
    Content,
    MarriageAnnouncementType,
    MarriageSuccessMetadata,
    Moderation,
    Post,
    VisibilitySettings,
)
from app.community.repositories.post import PostRepository
from app.community.services.exceptions import ValidationException
from app.events.event_types import EventType

logger = logging.getLogger(__name__)


class MarriageSuccessService:
    """
    Handles admin-only creation and management of MARRIAGE_SUCCESS posts.

    Responsibilities:
    - Validates request inputs (person1 != person2, correct metadata rules).
    - Checks for existing active announcements for the same profile(s).
    - Creates the Post document via PostRepository (APPROVED, publishedAt = now).
    - Publishes MARRIAGE_SUCCESS_CREATED event for downstream notifications.
    """

    def __init__(self, post_repo: PostRepository, event_publisher: Any = None) -> None:
        self.post_repo = post_repo
        self.event_publisher = event_publisher

    async def create_marriage_announcement(
        self,
        admin_id: str,
        admin_author: AuthorSnapshot,
        announcement_type: MarriageAnnouncementType,
        person1_profile_id: str,
        content: Content,
        person2_profile_id: Optional[str] = None,
        visibility: Visibility = Visibility.PUBLIC,
    ) -> Post:
        """
        Create and publish a MARRIAGE_SUCCESS post on behalf of an admin.

        Args:
            admin_id: Firebase UID of the acting admin.
            admin_author: AuthorSnapshot for the admin.
            announcement_type: SINGLE_PERSON or COUPLE.
            person1_profile_id: Profile ID of the first person.
            content: Post content (title, body, images).
            person2_profile_id: Profile ID of second person (required for COUPLE).
            visibility: Feed visibility (defaults to PUBLIC).

        Raises:
            ValidationException: If person1 == person2, or an active duplicate exists.
        """

        # Guard: person1 != person2
        if (
            announcement_type == MarriageAnnouncementType.COUPLE
            and person2_profile_id
            and person1_profile_id == person2_profile_id
        ):
            raise ValidationException(
                "person1ProfileId and person2ProfileId must be different."
            )

        # Guard: no active duplicate for these profiles
        await self._check_no_active_duplicate(
            announcement_type=announcement_type,
            person1_profile_id=person1_profile_id,
            person2_profile_id=person2_profile_id,
        )

        # Build domain model — Phase 1 validator sets expiresAt = createdAt + 30 days
        now = datetime.now(timezone.utc)
        metadata = MarriageSuccessMetadata(
            announcementType=announcement_type,
            person1ProfileId=person1_profile_id,
            person2ProfileId=person2_profile_id,
        )
        post = Post(
            type=PostType.MARRIAGE_SUCCESS,
            author=admin_author,
            content=content,
            metadata=metadata,
            moderation=Moderation(
                status=PostStatus.APPROVED,
                reviewedBy=admin_id,
                reviewedAt=now,
                approvalNotes="Admin-published marriage announcement",
            ),
            visibility=VisibilitySettings(visibility=visibility),
            createdAt=now,
            updatedAt=now,
            publishedAt=now,
        )

        # Persist
        created = await self.post_repo.create_post(post)
        logger.info(
            "MARRIAGE_SUCCESS post created: id=%s, admin=%s, type=%s, person1=%s, person2=%s",
            created.id, admin_id, announcement_type.value,
            person1_profile_id, person2_profile_id,
        )

        # Publish event
        if self.event_publisher:
            event_payload = {
                "postId": str(created.id),
                "person1ProfileId": person1_profile_id,
                "person2ProfileId": person2_profile_id,
                "createdByAdminId": admin_id,
                "announcementType": announcement_type.value,
                "publishedAt": created.publishedAt.isoformat() if created.publishedAt else None,
                "expiresAt": created.expiresAt.isoformat() if created.expiresAt else None,
            }
            await self.event_publisher.publish(
                EventType.MARRIAGE_SUCCESS_CREATED,
                event_payload,
            )

        return created

    async def _check_no_active_duplicate(
        self,
        announcement_type: MarriageAnnouncementType,
        person1_profile_id: str,
        person2_profile_id: Optional[str],
    ) -> None:
        """
        Prevent duplicate active MARRIAGE_SUCCESS announcements for the same profile(s).

        Queries active (non-expired, APPROVED) posts of the same announcementType.
        Raises ValidationException if any existing post shares a profile ID with
        the one being created.
        """
        existing_posts, _ = await self.post_repo.find_posts_by_admin(
            post_type=PostType.MARRIAGE_SUCCESS,
            statuses=[PostStatus.APPROVED],
            announcement_type=announcement_type.value,
            active=True,
            limit=10,
        )

        for post in existing_posts:
            if not isinstance(post.metadata, MarriageSuccessMetadata):
                continue
            meta = post.metadata

            profile_ids_in_post = {meta.person1ProfileId}
            if meta.person2ProfileId:
                profile_ids_in_post.add(meta.person2ProfileId)

            profiles_being_added = {person1_profile_id}
            if person2_profile_id:
                profiles_being_added.add(person2_profile_id)

            if profiles_being_added & profile_ids_in_post:
                raise ValidationException(
                    f"An active marriage announcement already exists for this profile. "
                    f"Existing post ID: {post.id}"
                )
