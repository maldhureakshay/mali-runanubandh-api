"""
Moderation Service module.

Implements business logic for administrative moderation of community posts.
"""

import logging
from typing import Any, List, Optional, Tuple

from app.community.enums import PostStatus, PostType

from app.community.models.post import Post
from app.community.repositories.post import PostRepository
from app.community.repositories.exceptions import DocumentNotFoundException
from app.community.services.exceptions import PostNotFoundException, InvalidPostStateException, PostDeletedException

from app.events.event_types import EventType

logger = logging.getLogger(__name__)


class ModerationService:
    """
    Handles moderation operations performed by administrators and moderators.
    """

    def __init__(self, post_repo: PostRepository, event_publisher: Any = None, post_review_service: Any = None) -> None:
        """
        Dependency injects PostRepository, EventPublisher, and PostReviewService.
        """
        self.post_repo = post_repo
        self.event_publisher = event_publisher
        self.post_review_service = post_review_service

    async def approve_post(self, post_id: str, admin_id: str, approval_notes: Optional[str] = None) -> Post:
        """
        Approve a pending post and set its status to APPROVED.
        """
        try:
            post = await self.post_repo.get_post(post_id)
        except DocumentNotFoundException:
            raise PostNotFoundException()

        status = post.moderation.status
        if status == PostStatus.DELETED:
            raise PostDeletedException("Cannot approve a deleted post.")
        if status == PostStatus.ARCHIVED:
            raise InvalidPostStateException("Cannot approve an archived post.")
            
        if status in (PostStatus.APPROVED, PostStatus.DRAFT, PostStatus.NEEDS_CHANGES):
            raise InvalidPostStateException(f"Cannot approve a post that is currently {status.value}.")

        if status != PostStatus.PENDING_REVIEW:
            raise InvalidPostStateException("Only posts in PENDING_REVIEW can be approved.")

        # Update in database
        updated_post = await self.post_repo.approve_post(post_id, admin_id, approval_notes)
        
        logger.info("Moderator Approved Post - Moderator ID: %s, Post ID: %s, Author ID: %s, Approval Time: %s", 
                    admin_id, post_id, updated_post.author.userId, updated_post.moderation.reviewedAt)
                    
        if self.event_publisher:
            event_payload = {
                "postId": str(updated_post.id),
                "authorId": updated_post.author.userId,
                "moderatorId": admin_id,
                "approvedAt": updated_post.moderation.reviewedAt.isoformat() if updated_post.moderation.reviewedAt else None,
                "publishedAt": updated_post.publishedAt.isoformat() if updated_post.publishedAt else None,
                "version": updated_post.moderation.version
            }
            await self.event_publisher.publish(
                EventType.POST_APPROVED,
                event_payload
            )
            
        if self.post_review_service:
            await self.post_review_service.record_action(
                post_id=str(updated_post.id),
                post_version=updated_post.moderation.version,
                author_id=updated_post.author.userId,
                moderator_id=admin_id,
                action=EventType.POST_APPROVED.value,
                status_before=status,
                status_after=updated_post.moderation.status,
                approval_notes=approval_notes
            )
            
        return updated_post

    async def request_changes(
        self,
        post_id: str,
        admin_id: str,
        review_comments: str,
        rejection_reason: Optional[str] = None
    ) -> Post:
        """
        Request changes for a submitted post.
        """
        try:
            post = await self.post_repo.get_post(post_id)
        except DocumentNotFoundException:
            raise PostNotFoundException()

        status = post.moderation.status
        if status in (PostStatus.DELETED, PostStatus.ARCHIVED, PostStatus.APPROVED, PostStatus.DRAFT, PostStatus.NEEDS_CHANGES):
            raise InvalidPostStateException(f"Cannot request changes on a post that is {status.value}.")

        if status != PostStatus.PENDING_REVIEW:
            raise InvalidPostStateException("Only posts in PENDING_REVIEW can be sent back for changes.")

        updated_post = await self.post_repo.request_changes(
            post_id=post_id,
            admin_id=admin_id,
            review_comments=review_comments,
            rejection_reason=rejection_reason
        )

        logger.info("Moderator Requested Changes - Moderator ID: %s, Post ID: %s, Author ID: %s", 
                    admin_id, post_id, updated_post.author.userId)

        if self.event_publisher:
            event_payload = {
                "postId": str(updated_post.id),
                "authorId": updated_post.author.userId,
                "moderatorId": admin_id,
                "reviewComments": updated_post.moderation.reviewComments,
                "reviewedAt": updated_post.moderation.reviewedAt.isoformat() if updated_post.moderation.reviewedAt else None
            }
            await self.event_publisher.publish(
                EventType.POST_NEEDS_CHANGES,
                event_payload
            )

        if self.post_review_service:
            await self.post_review_service.record_action(
                post_id=str(updated_post.id),
                post_version=updated_post.moderation.version,
                author_id=updated_post.author.userId,
                moderator_id=admin_id,
                action=EventType.POST_NEEDS_CHANGES.value,
                status_before=status,
                status_after=updated_post.moderation.status,
                review_comments=review_comments,
                rejection_reason=rejection_reason
            )

        return updated_post

    async def reject_post(self, post_id: str, admin_id: str, reason: str) -> Post:
        """
        Reject a pending post and set its status to REJECTED with a reason.
        """
        try:
            post = await self.post_repo.reject_post(post_id, admin_id, reason)
            logger.info("Post rejected: ID %s rejected by admin %s. Reason: %s", post_id, admin_id, reason)
            if self.event_publisher:
                await self.event_publisher.publish(
                    EventType.POST_REJECTED,
                    post.model_dump(by_alias=True)
                )
            return post
        except DocumentNotFoundException:
            raise PostNotFoundException()

    async def restore_post(self, post_id: str, admin_id: str) -> Post:
        """
        Restore a deleted or rejected post, resetting status to APPROVED.
        """
        try:
            old_post = await self.post_repo.get_post(post_id)
            post = await self.post_repo.restore_post(post_id, admin_id)
            logger.info("Post restored: ID %s restored by admin %s.", post_id, admin_id)
            if self.event_publisher:
                await self.event_publisher.publish(
                    EventType.POST_APPROVED,
                    post.model_dump(by_alias=True)
                )
            if self.post_review_service:
                await self.post_review_service.record_action(
                    post_id=str(post.id),
                    post_version=post.moderation.version,
                    author_id=post.author.userId,
                    moderator_id=admin_id,
                    action="POST_RESTORED",
                    status_before=old_post.moderation.status,
                    status_after=post.moderation.status
                )
            return post
        except DocumentNotFoundException:
            raise PostNotFoundException()

    async def delete_post(self, post_id: str, admin_id: str) -> Post:
        """
        Force-soft-delete a post by an administrator/moderator.
        """
        try:
            # First check if post exists
            old_post = await self.post_repo.get_post(post_id)
            await self.post_repo.delete_post(post_id)
            # Re-fetch to return the updated post model
            updated = await self.post_repo.get_post(post_id)
            logger.info("Post deleted: ID %s soft-deleted by admin %s.", post_id, admin_id)
            if self.event_publisher:
                await self.event_publisher.publish(
                    EventType.POST_DELETED,
                    updated.model_dump(by_alias=True)
                )
            if self.post_review_service:
                await self.post_review_service.record_action(
                    post_id=str(updated.id),
                    post_version=updated.moderation.version,
                    author_id=updated.author.userId,
                    moderator_id=admin_id,
                    action="POST_ARCHIVED",
                    status_before=old_post.moderation.status,
                    status_after=updated.moderation.status
                )
            return updated
        except DocumentNotFoundException:
            raise PostNotFoundException()

    async def get_pending_posts(
        self,
        moderator_id: str,
        post_type: Optional[PostType] = None,
        author_name: Optional[str] = None,
        author_id: Optional[str] = None,
        submission_date: Optional[str] = None,
        sort_order: int = -1,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> Tuple[List[Post], Optional[str]]:
        """
        Retrieves submitted posts awaiting review based on filters.
        """
        logger.info(
            "Moderator %s viewing moderation queue with filters - type: %s, author_name: %s, author_id: %s, date: %s",
            moderator_id, post_type, author_name, author_id, submission_date
        )
        return await self.post_repo.find_pending_posts(
            post_type=post_type,
            author_name=author_name,
            author_id=author_id,
            submission_date=submission_date,
            sort_order=sort_order,
            limit=limit,
            cursor=cursor
        )

    async def get_post_for_review(self, post_id: str, moderator_id: str) -> Post:
        """
        Retrieve complete post details for moderation review.
        """
        try:
            post = await self.post_repo.get_post_for_review(post_id)
            if post.moderation.status != PostStatus.PENDING_REVIEW:
                raise PostNotFoundException("Post is not in PENDING_REVIEW state.")
            
            logger.info("Moderator %s opened post %s for review.", moderator_id, post_id)
            return post
        except DocumentNotFoundException:
            raise PostNotFoundException()

    async def get_admin_posts(
        self,
        admin_id: str,
        post_type: PostType,
        statuses: Optional[List[PostStatus]] = None,
        announcement_type: Optional[str] = None,
        active: Optional[bool] = None,
        created_date: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Post], Optional[str]]:
        """
        Retrieve posts of a given type for admin management.

        Supports filtering by status list, announcementType, active/expired state,
        and created date. Reuses existing cursor-based pagination.
        """
        logger.info(
            "Admin %s listing posts: type=%s, statuses=%s, announcementType=%s, active=%s, date=%s",
            admin_id, post_type, statuses, announcement_type, active, created_date,
        )
        return await self.post_repo.find_posts_by_admin(
            post_type=post_type,
            statuses=statuses,
            announcement_type=announcement_type,
            active=active,
            created_date=created_date,
            limit=limit,
            cursor=cursor,
        )

    async def get_post_details(self, post_id: str, admin_id: str) -> Post:
        """
        Retrieve full post details for an admin without status restriction.

        Unlike get_post_for_review, this method works on posts in any status
        (e.g. APPROVED, ARCHIVED) and is intended for admin detail views.
        """
        try:
            post = await self.post_repo.get_post(post_id)
            logger.info("Admin %s viewed post %s (status=%s).", admin_id, post_id, post.moderation.status)
            return post
        except DocumentNotFoundException:
            raise PostNotFoundException()
