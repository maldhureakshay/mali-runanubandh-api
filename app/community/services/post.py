"""
Post Service module.

Implements all business logic workflows and rules verification for Community Posts.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from app.community.enums import PostStatus, PostType, Visibility
from app.community.models.post import AuthorSnapshot, Content, Moderation, Post, PostMetadata, VisibilitySettings
from app.community.repositories.post import PostRepository
from app.community.repositories.exceptions import DocumentNotFoundException
from app.community.services.exceptions import (
    PostNotFoundException,
    PostDeletedException,
    ValidationException,
)
from app.events.event_types import EventType

logger = logging.getLogger(__name__)


class PostService:
    """
    Handles business validations, state transitions, feeds, and analytics metrics for Posts.
    """

    def __init__(self, post_repo: PostRepository, event_publisher: Any = None, post_review_service: Any = None) -> None:
        """
        Constructor injects PostRepository dependency and optional EventPublisher and PostReviewService.
        """
        self.post_repo = post_repo
        self.event_publisher = event_publisher
        self.post_review_service = post_review_service

    async def create_post(
        self,
        content: Content,
        post_type: PostType,
        author: AuthorSnapshot,
        metadata: Optional[PostMetadata] = None,
        visibility: Optional[VisibilitySettings] = None,
        status: Optional[PostStatus] = None,
        session: Any = None
    ) -> Post:
        """
        Validate and create a new community post.
        
        Args:
            content: The text and images payload.
            post_type: The PostType category.
            author: Information on the creating author.
            metadata: Associated category metadata (e.g. SuccessStoryMetadata).
            visibility: Audience options.
            session: Optional database session/transaction.
        """
        try:
            # Construct domain Post object (triggers automated validations)
            post = Post(
                type=post_type,
                author=author,
                content=content,
                metadata=metadata,
                visibility=visibility or VisibilitySettings(visibility=Visibility.PUBLIC),
                moderation=Moderation(status=status or PostStatus.PENDING_REVIEW),
                createdAt=datetime.now(timezone.utc),
                updatedAt=datetime.now(timezone.utc)
            )
        except ValidationError as e:
            logger.warning("Pydantic validation failed during post creation: %s", e)
            raise ValidationException(message="Input validation failed for post.", data={"errors": e.errors()})

        # Save to database
        # BaseRepository functions can accept standard mongo session if configured in future
        created_post = await self.post_repo.create_post(post)
        logger.info("Post created successfully with ID: %s by user: %s", created_post.id, author.userId)
        if self.event_publisher:
            await self.event_publisher.publish(
                EventType.POST_CREATED,
                created_post.model_dump(by_alias=True)
            )
        return created_post

    async def update_post(
        self,
        post_id: str,
        content: Optional[Content] = None,
        metadata: Optional[PostMetadata] = None,
        visibility: Optional[VisibilitySettings] = None,
        status: Optional[PostStatus] = None,
        session: Any = None
    ) -> Post:
        """
        Update the post's content, metadata, visibility, or status.
        """
        # Fetch current post state
        post = await self.get_post(post_id)

        update_dict: Dict[str, Any] = {}
        
        # Build changes dictionary
        if content is not None:
            update_dict["content"] = content.model_dump()
        if metadata is not None:
            update_dict["metadata"] = metadata.model_dump()
        if visibility is not None:
            update_dict["visibility"] = visibility.model_dump()
        if status is not None:
            update_dict["moderation.status"] = status.value

        # Build modified post data to test validation rules
        merged_data = post.model_dump()
        if content is not None:
            merged_data["content"] = content.model_dump()
        if metadata is not None:
            merged_data["metadata"] = metadata.model_dump()
        if visibility is not None:
            merged_data["visibility"] = visibility.model_dump()
        if status is not None:
            if "moderation" not in merged_data or merged_data["moderation"] is None:
                merged_data["moderation"] = {}
            merged_data["moderation"]["status"] = status.value

        try:
            # Validate complete model with updates merged
            Post.model_validate(merged_data)
        except ValidationError as e:
            logger.warning("Validation failed for post update on ID %s: %s", post_id, e)
            raise ValidationException(message="Update violates post validation rules.", data={"errors": e.errors()})

        updated = await self.post_repo.update_post(post_id, update_dict)
        logger.info("Post %s updated successfully.", post_id)
        if self.event_publisher:
            await self.event_publisher.publish(
                EventType.POST_UPDATED,
                updated.model_dump(by_alias=True)
            )

        # If we auto-resubmitted, actually execute the submit_post logic to increment version & clear reasons
        if post.moderation.status == PostStatus.NEEDS_CHANGES and content is not None and status is None:
            updated = await self.submit_post(post_id, updated.author.userId)
            
        return updated

    async def delete_post(self, post_id: str, session: Any = None) -> bool:
        """
        Soft delete post.
        """
        try:
            # Validate post exists
            post = await self.get_post(post_id)
            await self.post_repo.delete_post(post_id)
            logger.info("Post %s soft deleted successfully.", post_id)
            if self.event_publisher:
                await self.event_publisher.publish(
                    EventType.POST_DELETED,
                    post.model_dump(by_alias=True)
                )
            return True
        except DocumentNotFoundException:
            raise PostNotFoundException()

    async def submit_post(self, post_id: str, user_id: str, session: Any = None) -> Post:
        """
        Submit a draft or needs_changes post for review.
        """
        post = await self.get_post(post_id)
        
        if post.author.userId != user_id:
            raise ValidationException("Only the author can submit this post.")
            
        if post.moderation.status in (PostStatus.APPROVED, PostStatus.ARCHIVED, PostStatus.DELETED, PostStatus.PENDING_REVIEW):
            raise ValidationException(f"Cannot submit a post that is already {post.moderation.status.value}.")
            
        is_resubmission = post.moderation.status == PostStatus.NEEDS_CHANGES
            
        submitted = await self.post_repo.submit_post(post_id, is_resubmission=is_resubmission)
        
        if is_resubmission:
            logger.info("Author Resubmitted Post - Post ID: %s, Author ID: %s", post_id, user_id)
            if self.event_publisher:
                event_payload = {
                    "postId": str(submitted.id),
                    "authorId": submitted.author.userId,
                    "version": submitted.moderation.version,
                    "resubmittedAt": submitted.moderation.resubmittedAt.isoformat() if submitted.moderation.resubmittedAt else None
                }
                await self.event_publisher.publish(
                    EventType.POST_RESUBMITTED,
                    event_payload
                )
            if self.post_review_service:
                await self.post_review_service.record_action(
                    post_id=str(submitted.id),
                    post_version=submitted.moderation.version,
                    author_id=submitted.author.userId,
                    action=EventType.POST_RESUBMITTED.value,
                    status_before=post.moderation.status,
                    status_after=submitted.moderation.status
                )
        else:
            logger.info("Post %s submitted for review by user %s.", post_id, user_id)
            if self.event_publisher:
                await self.event_publisher.publish(
                    EventType.POST_SUBMITTED,
                    submitted.model_dump(by_alias=True)
                )
            if self.post_review_service:
                await self.post_review_service.record_action(
                    post_id=str(submitted.id),
                    post_version=submitted.moderation.version,
                    author_id=submitted.author.userId,
                    action=EventType.POST_SUBMITTED.value,
                    status_before=post.moderation.status,
                    status_after=submitted.moderation.status
                )
            
        return submitted
    async def approve_post(self, post_id: str, admin_id: str, session: Any = None) -> Post:
        """
        Transition post workflow status to APPROVED.
        """
        post = await self.get_post(post_id)
        if post.moderation.status == PostStatus.DELETED:
            raise PostDeletedException("Cannot approve a deleted post.")
            
        approved = await self.post_repo.approve_post(post_id, admin_id)
        logger.info("Post %s approved by admin %s.", post_id, admin_id)
        return approved

    async def reject_post(self, post_id: str, admin_id: str, reason: str, session: Any = None) -> Post:
        """
        Transition post workflow status to REJECTED.
        """
        post = await self.get_post(post_id)
        if post.moderation.status == PostStatus.DELETED:
            raise PostDeletedException("Cannot reject a deleted post.")
            
        rejected = await self.post_repo.reject_post(post_id, admin_id, reason)
        logger.info("Post %s rejected by admin %s for: %s", post_id, admin_id, reason)
        return rejected

    async def publish_post(self, post_id: str, session: Any = None) -> Post:
        """
        Publishes the post, changing status to APPROVED and setting publishedAt timestamp.
        """
        post = await self.get_post(post_id)
        if post.moderation.status == PostStatus.DELETED:
            raise PostDeletedException("Cannot publish a deleted post.")
            
        published = await self.post_repo.publish_post(post_id)
        logger.info("Post %s published successfully.", post_id)
        return published

    async def get_post(self, post_id: str) -> Post:
        """
        Retrieve post by ID. Throws PostNotFoundException if deleted or missing.
        """
        try:
            post = await self.post_repo.get_post(post_id)
            if post.moderation.status == PostStatus.DELETED:
                raise PostNotFoundException("The requested post has been deleted.")
            return post
        except DocumentNotFoundException:
            raise PostNotFoundException()

    async def get_feed(
        self,
        visibility: Visibility = Visibility.PUBLIC,
        limit: int = 20,
        cursor: Optional[str] = None,
        post_type: Optional[PostType] = None
    ) -> Tuple[List[Post], Optional[str]]:
        """
        Retrieve list of active, approved feed posts.
        """
        if post_type:
            # Query posts by type specifically
            return await self.post_repo.find_posts_by_type(post_type, limit=limit, cursor=cursor)
            
        return await self.post_repo.find_feed(visibility=visibility, limit=limit, cursor=cursor)

    async def get_posts_by_author(
        self,
        user_id: str,
        limit: int = 20,
        cursor: Optional[str] = None,
        status: Optional[PostStatus] = None
    ) -> Tuple[List[Post], Optional[str]]:
        """
        Retrieve posts written by a specific user.
        """
        return await self.post_repo.find_posts_by_author(user_id, limit=limit, cursor=cursor, status=status)
