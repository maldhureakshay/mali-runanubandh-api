"""
Comment Service module.

Implements business logic for managing Comments on community posts.
"""

from datetime import datetime, timezone
import logging
from typing import Any, List, Optional, Tuple

from app.community.models.comment import Comment
from app.community.models.post import AuthorSnapshot
from app.community.enums import PostStatus, PostType
from app.community.repositories.comment import CommentRepository
from app.community.repositories.post import PostRepository
from app.community.repositories.exceptions import DocumentNotFoundException
from app.core.exceptions import ForbiddenException
from app.community.services.exceptions import (
    CommentNotFoundException,
    PostDeletedException,
    PostNotFoundException,
    ValidationException,
)

from app.events.event_types import EventType

logger = logging.getLogger(__name__)


class CommentService:
    """
    Orchestrates business operations for posting, listing, editing, and soft-deleting comments.
    """

    def __init__(self, comment_repo: CommentRepository, post_repo: PostRepository, event_publisher: Any = None) -> None:
        """
        Dependency injects CommentRepository, PostRepository and optional EventPublisher.
        """
        self.comment_repo = comment_repo
        self.post_repo = post_repo
        self.event_publisher = event_publisher

    async def create_comment(
        self,
        post_id: str,
        author: AuthorSnapshot,
        comment_text: str,
        session: Any = None
    ) -> Comment:
        """
        Add a comment to an active community post and increment comment statistics.
        """
        # Trim whitespace
        clean_text = comment_text.strip()
        if not clean_text:
            raise ValueError("Comment text cannot be empty.")
            
        try:
            # 1. Verify post exists
            post = await self.post_repo.get_post(post_id)
            
            # 2. Prevent commenting on deleted or rejected posts
            if post.moderation.status == PostStatus.DELETED:
                raise PostDeletedException("Cannot comment on a deleted post.")
            if post.moderation.status == PostStatus.NEEDS_CHANGES:
                raise PostDeletedException("Cannot comment on a rejected post.")
                
            # Birthday checks
            if post.type == PostType.BIRTHDAY:
                if post.moderation.status != PostStatus.APPROVED:
                    raise ValidationException("Cannot comment on a non-approved birthday post.")
                if post.expiresAt and post.expiresAt <= datetime.now(timezone.utc):
                    raise ValidationException("Cannot comment on an expired birthday post.")
                
        except DocumentNotFoundException:
            raise PostNotFoundException("Cannot comment on a post that does not exist.")

        # 3. Create comment document
        comment = Comment(
            postId=post_id,
            author=author,
            comment=clean_text,
            edited=False,
            createdAt=datetime.now(timezone.utc),
            updatedAt=datetime.now(timezone.utc)
        )
        
        # 4. Save comment to DB
        created_comment = await self.comment_repo.create_comment(comment)

        # 5. Increment comment count atomically
        await self.post_repo.increment_comments(post_id)
        
        logger.info("Comment created: ID %s on post %s by user %s.", created_comment.id, post_id, author.userId)
        if self.event_publisher:
            if post.type == PostType.BIRTHDAY:
                await self.event_publisher.publish(
                    EventType.BIRTHDAY_WISH_CREATED,
                    {
                        "postId": post_id,
                        "birthdayProfileId": post.metadata.profileId,
                        "commenterUserId": author.userId,
                        "commentId": str(created_comment.id)
                    }
                )
            else:
                await self.event_publisher.publish(
                    EventType.COMMENT_CREATED,
                    created_comment.model_dump(by_alias=True)
                )
        return created_comment

    async def update_comment(
        self,
        comment_id: str,
        current_user_uid: str,
        new_text: str,
        session: Any = None
    ) -> Comment:
        """
        Update the text of a comment if the requesting user is the owner.
        """
        clean_text = new_text.strip()
        if not clean_text:
            raise ValueError("Comment text cannot be empty.")

        try:
            comment = await self.comment_repo.get_comment(comment_id)
        except DocumentNotFoundException:
            raise CommentNotFoundException()

        # Enforce authorization: Only owner can edit
        if comment.author.userId != current_user_uid:
            logger.warning(
                "Authorization failure: User %s attempted to edit comment %s owned by %s.",
                current_user_uid,
                comment_id,
                comment.author.userId
            )
            raise ForbiddenException(message="You do not have permission to edit this comment.")

        updated = await self.comment_repo.update_comment(comment_id, clean_text)
        logger.info("Comment updated: ID %s by user %s.", comment_id, current_user_uid)
        return updated

    async def delete_comment(
        self,
        comment_id: str,
        current_user_uid: str,
        is_admin: bool,
        session: Any = None
    ) -> bool:
        """
        Soft delete a comment and decrement the target post's comment count.
        
        Only the owner or an ADMIN can delete.
        """
        try:
            comment = await self.comment_repo.get_comment(comment_id)
        except DocumentNotFoundException:
            raise CommentNotFoundException()

        # Enforce authorization: Only owner or ADMIN can delete
        if comment.author.userId != current_user_uid and not is_admin:
            logger.warning(
                "Authorization failure: User %s attempted to delete comment %s owned by %s.",
                current_user_uid,
                comment_id,
                comment.author.userId
            )
            raise ForbiddenException(message="You do not have permission to delete this comment.")

        # Soft delete in DB
        await self.comment_repo.delete_comment(comment_id)

        # Decrement comment count atomically
        try:
            await self.post_repo.decrement_comments(comment.postId)
        except Exception as e:
            logger.warning("Failed to decrement comment count for post %s: %s", comment.postId, e)

        logger.info("Comment deleted: ID %s by user %s.", comment_id, current_user_uid)
        return True

    async def get_comments(
        self,
        post_id: str,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> Tuple[List[Comment], Optional[str]]:
        """
        Retrieve a list of active comments for a post.
        """
        # Validate that post exists
        try:
            await self.post_repo.get_post(post_id)
        except DocumentNotFoundException:
            raise PostNotFoundException()

        return await self.comment_repo.find_by_post(post_id, limit=limit, cursor=cursor)
