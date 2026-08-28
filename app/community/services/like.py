"""
Like Service module.

Implements business logic for managing Likes on community posts.
"""

from datetime import datetime, timezone
import logging
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.community.models.like import Like
from app.community.enums import PostStatus
from app.community.repositories.like import LikeRepository
from app.community.repositories.post import PostRepository
from app.community.repositories.exceptions import DocumentNotFoundException
from app.community.services.exceptions import (
    DuplicateLikeException,
    PostDeletedException,
    PostNotFoundException,
)

from app.events.event_types import EventType

logger = logging.getLogger(__name__)


class LikeService:
    """
    Orchestrates business operations for liking and unliking community posts.
    """

    def __init__(self, like_repo: LikeRepository, post_repo: PostRepository, event_publisher: Any = None) -> None:
        """
        Dependency injects LikeRepository, PostRepository and optional EventPublisher.
        """
        self.like_repo = like_repo
        self.post_repo = post_repo
        self.event_publisher = event_publisher

    async def like_post(self, post_id: str, user_id: str, session: Any = None) -> Like:
        """
        Like a post, registering the reaction and incrementing the like counter atomically.
        """
        # 1. Verify post exists
        try:
            post = await self.post_repo.get_post(post_id)
            
            # 2. Prevent liking deleted or rejected posts
            if post.moderation.status == PostStatus.DELETED:
                raise PostDeletedException("Cannot like a deleted post.")
            if post.moderation.status == PostStatus.NEEDS_CHANGES:
                raise PostDeletedException("Cannot like a rejected post.")
                
        except DocumentNotFoundException:
            raise PostNotFoundException("Cannot like a post that does not exist.")

        # 3. Prevent duplicate likes (idempotency safety check)
        already_liked = await self.like_repo.has_user_liked(post_id, user_id)
        if already_liked:
            logger.warning("Duplicate like attempt: User %s on post %s.", user_id, post_id)
            raise DuplicateLikeException()

        # 4. Create and store reaction
        like_record = Like(
            postId=post_id,
            userId=user_id,
            createdAt=datetime.now(timezone.utc)
        )
        
        try:
            created = await self.like_repo.create_like(like_record)
        except DuplicateKeyError:
            logger.warning("Duplicate like attempt: User %s on post %s (DB constraint).", user_id, post_id)
            raise DuplicateLikeException()

        # 5. Increment count atomically
        await self.post_repo.increment_likes(post_id)
        
        logger.info("Post liked: User %s liked post %s.", user_id, post_id)
        if self.event_publisher:
            await self.event_publisher.publish(
                EventType.POST_LIKED,
                created.model_dump(by_alias=True)
            )
        return created

    async def unlike_post(self, post_id: str, user_id: str, session: Any = None) -> bool:
        """
        Unlike a post, removing the reaction and decrementing the like counter atomically.
        
        Idempotent: If user has not liked the post, returns True without raising an error.
        """
        # 1. Check if like exists
        already_liked = await self.like_repo.has_user_liked(post_id, user_id)
        if not already_liked:
            logger.info("User %s tried unliking post %s which they didn't like. Idempotent success.", user_id, post_id)
            return True

        # 2. Remove reaction record
        try:
            await self.like_repo.remove_like(post_id, user_id)
        except DocumentNotFoundException:
            return True

        # 3. Decrement count atomically
        try:
            await self.post_repo.decrement_likes(post_id)
        except Exception as e:
            logger.warning("Failed to decrement like count for post %s: %s", post_id, e)

        logger.info("Post unliked: User %s unliked post %s.", user_id, post_id)
        if self.event_publisher:
            await self.event_publisher.publish(
                EventType.POST_UNLIKED,
                {"postId": post_id, "userId": user_id}
            )
        return True

    async def has_user_liked(self, post_id: str, user_id: str) -> bool:
        """
        Check if user liked a specific post.
        """
        return await self.like_repo.has_user_liked(post_id, user_id)

    async def get_post_likers(self, post_id: str) -> List[dict]:
        """
        Retrieves a list of AuthorSnapshots of users who liked this post.
        """
        # Fetch likes from repository
        likes, _ = await self.like_repo.find_many({"postId": post_id}, limit=100)
        
        from app.community.routers.utils import _fetch_user_from_firestore
        from app.community.models.post import AuthorSnapshot
        from fastapi.concurrency import run_in_threadpool
        
        likers_snapshots = []
        for l in likes:
            user_id = l.get("userId")
            if not user_id:
                continue
            
            user_data = await run_in_threadpool(_fetch_user_from_firestore, user_id)
            profile_ids = user_data.get("profile_ids", [])
            profile_id = profile_ids[0] if profile_ids else "unknown"
            
            snapshot = AuthorSnapshot(
                userId=user_id,
                profileId=profile_id,
                fullName=user_data.get("displayName", "Community Member"),
                verified=user_data.get("is_verified", False),
                paidMember=user_data.get("status") == "premium" or user_data.get("paidMember", False)
            )
            likers_snapshots.append(snapshot.model_dump(by_alias=True))
            
        return likers_snapshots
