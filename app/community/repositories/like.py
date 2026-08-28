"""
Like Repository module.

Responsible for database operations on Likes collection.
"""

import logging
from typing import List, Set

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.community.models.like import Like
from app.community.repositories.base import BaseRepository
from app.community.repositories.exceptions import DocumentNotFoundException, RepositoryException

logger = logging.getLogger(__name__)


class LikeRepository(BaseRepository):
    """
    Handles database operations for Likes.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """
        Initializes the repository with the likes collection name.
        """
        super().__init__(db, "likes")

    async def create_like(self, like: Like) -> Like:
        """
        Insert a new like.
        """
        like_data = like.model_dump(by_alias=True, exclude={"id"})
        if like.id:
            like_data["_id"] = ObjectId(like.id)
            
        created = await self.create(like_data)
        return Like.model_validate(created)

    async def remove_like(self, post_id: str, user_id: str) -> bool:
        """
        Delete a like by post ID and user ID.
        """
        try:
            result = await self.collection.delete_one({"postId": post_id, "userId": user_id})
            if result.deleted_count == 0:
                raise DocumentNotFoundException("Like record not found.")
            return True
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error removing like for post %s, user %s: %s", post_id, user_id, e)
            raise RepositoryException(message=f"Database delete error: {e}")

    async def has_user_liked(self, post_id: str, user_id: str) -> bool:
        """
        Check if a user has liked a specific post.
        """
        return await self.exists({"postId": post_id, "userId": user_id})

    async def get_liked_post_ids(self, post_ids: List[str], user_id: str) -> Set[str]:
        """
        Finds which of the post_ids in a list have been liked by a user.
        Optimized for feed pagination.
        """
        try:
            cursor = self.collection.find(
                {"postId": {"$in": post_ids}, "userId": user_id},
                {"postId": 1}
            )
            docs = await cursor.to_list(length=len(post_ids))
            return {doc["postId"] for doc in docs}
        except Exception as e:
            logger.error("Error batch getting liked posts for user %s: %s", user_id, e)
            return set()

    async def count_by_post(self, post_id: str) -> int:
        """
        Get total like count for a post.
        """
        return await self.count({"postId": post_id})
