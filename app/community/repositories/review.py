"""
Post Review Repository module.

Provides database access layer for the post_reviews collection.
"""

from typing import Any, Dict, List, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timezone

from app.community.repositories.base import BaseRepository
from app.community.models.review import PostReview


class PostReviewRepository(BaseRepository):
    """
    Repository for managing post review history records in MongoDB.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, "post_reviews")

    async def insert_review(self, review_data: Dict[str, Any]) -> PostReview:
        """
        Insert a new review record.
        """
        if "createdAt" not in review_data:
            review_data["createdAt"] = datetime.now(timezone.utc)
            
        doc = await self.create(review_data)
        return PostReview.model_validate(doc)

    async def get_reviews_for_post(
        self, 
        post_id: str, 
        sort_order: int = 1, 
        limit: int = 100
    ) -> List[PostReview]:
        """
        Retrieve all review records for a specific post.
        sort_order: 1 for oldest first (ascending), -1 for newest first (descending)
        """
        # We don't necessarily need cursor pagination for this specific use case, 
        # as a post's review history is typically small.
        docs, _ = await self.find_many(
            filters={"postId": post_id},
            sort=[("createdAt", sort_order)],
            limit=limit
        )
        return [PostReview.model_validate(doc) for doc in docs]
