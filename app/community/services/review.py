"""
Post Review Service module.

Coordinates creation and retrieval of moderation review history.
"""

import logging
from typing import List, Optional
from datetime import datetime, timezone

from app.community.enums import PostStatus
from app.community.models.review import PostReview
from app.community.repositories.review import PostReviewRepository
from app.community.repositories.post import PostRepository
from app.community.services.exceptions import ValidationException, PostNotFoundException
from app.community.repositories.exceptions import DocumentNotFoundException

logger = logging.getLogger(__name__)


class PostReviewService:
    """
    Handles business logic for the append-only post review history.
    """

    def __init__(self, review_repo: PostReviewRepository, post_repo: PostRepository) -> None:
        self.review_repo = review_repo
        self.post_repo = post_repo

    async def record_action(
        self,
        post_id: str,
        post_version: int,
        author_id: str,
        action: str,
        status_before: PostStatus,
        status_after: PostStatus,
        moderator_id: Optional[str] = None,
        review_comments: Optional[str] = None,
        approval_notes: Optional[str] = None,
        rejection_reason: Optional[str] = None
    ) -> PostReview:
        """
        Record a moderation action into the review history.
        """
        review_data = {
            "postId": post_id,
            "postVersion": post_version,
            "authorId": author_id,
            "moderatorId": moderator_id,
            "action": action,
            "statusBefore": status_before.value,
            "statusAfter": status_after.value,
            "reviewComments": review_comments,
            "approvalNotes": approval_notes,
            "rejectionReason": rejection_reason,
            "createdAt": datetime.now(timezone.utc)
        }
        
        # Filter out None values to keep document clean
        review_data = {k: v for k, v in review_data.items() if v is not None}
        
        review = await self.review_repo.insert_review(review_data)
        logger.info("Review History Created - Moderator ID: %s, Post ID: %s, Action: %s", 
                    moderator_id or "SYSTEM", post_id, action)
        return review

    async def get_review_history(
        self, 
        post_id: str, 
        user_id: str,
        user_roles: List[str],
        sort_order: int = 1
    ) -> List[PostReview]:
        """
        Retrieve the review history for a post.
        Validates authorization: only ADMIN, MODERATOR, or the post author can view.
        """
        try:
            post = await self.post_repo.get_post(post_id)
        except DocumentNotFoundException:
            raise PostNotFoundException(f"Post {post_id} not found.")

        is_privileged = any(role in ["ADMIN", "MODERATOR"] for role in user_roles)
        is_author = post.author.userId == user_id

        if not is_privileged and not is_author:
            # We raise a validation exception, which can be mapped to 403 or 400. 
            # In typical FastAPI setups, raising HTTPException(403) directly is router-layer,
            # but we can return a specific exception here. Let's raise an exception with a specific message.
            from app.core.exceptions import UnauthorizedException
            # Since UnauthorizedException maps to 401, we might need a ForbiddenException. 
            # The prompt says "All other users receive 403 Forbidden". We can use a custom exception or standard FastAPI HTTPException.
            # We'll use a fast API HTTPException here for simplicity, or just a ValidationException that maps to 403.
            # Let's import HTTPException from fastapi.
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view the moderation history for this post."
            )

        reviews = await self.review_repo.get_reviews_for_post(post_id, sort_order=sort_order)
        logger.info("History Retrieved - User ID: %s, Post ID: %s, Count: %d", user_id, post_id, len(reviews))
        return reviews
