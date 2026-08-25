"""
Vote Repository module.

Responsible for database operations on Poll Votes collection.
"""

import logging
from typing import Any, Dict, List, Set

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.community.models.poll_vote import PollVote
from app.community.repositories.base import BaseRepository
from app.community.repositories.exceptions import RepositoryException

logger = logging.getLogger(__name__)


class VoteRepository(BaseRepository):
    """
    Handles database operations for Poll Votes.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """
        Initializes the repository with the poll_votes collection name.
        """
        super().__init__(db, "poll_votes")

    async def create_vote(self, vote: PollVote) -> PollVote:
        """
        Insert a new vote cast.
        """
        vote_data = vote.model_dump(by_alias=True, exclude={"id"})
        if vote.id:
            vote_data["_id"] = ObjectId(vote.id)
            
        created = await self.create(vote_data)
        return PollVote.model_validate(created)

    async def get_user_votes(self, post_id: str, user_id: str) -> List[PollVote]:
        """
        Retrieve all votes cast by a specific user on a specific poll post.
        """
        try:
            cursor = self.collection.find({"postId": post_id, "userId": user_id})
            docs = await cursor.to_list(length=100)
            return [PollVote.model_validate(d) for d in docs]
        except Exception as e:
            logger.error("Error retrieving user votes: %s", e)
            raise RepositoryException(message=f"Database query error: {e}")

    async def has_user_voted(self, post_id: str, user_id: str) -> bool:
        """
        Check if user voted at all on a specific post.
        """
        return await self.exists({"postId": post_id, "userId": user_id})

    async def delete_user_votes(self, post_id: str, user_id: str) -> int:
        """
        Delete all votes cast by a specific user on a specific poll post.
        """
        try:
            result = await self.collection.delete_many({"postId": post_id, "userId": user_id})
            return result.deleted_count
        except Exception as e:
            logger.error("Error deleting user votes: %s", e)
            raise RepositoryException(message=f"Database delete error: {e}")

    async def get_user_voted_options_batch(self, post_ids: List[str], user_id: str) -> Dict[str, List[str]]:
        """
        Batch fetches user votes for multiple posts.
        Optimizes feed rendering to prevent N+1 query loops.
        """
        try:
            cursor = self.collection.find({"postId": {"$in": post_ids}, "userId": user_id})
            docs = await cursor.to_list(length=len(post_ids) * 10)
            
            res: Dict[str, List[str]] = {}
            for doc in docs:
                p_id = doc["postId"]
                opt_id = doc["optionId"]
                res.setdefault(p_id, []).append(opt_id)
            return res
        except Exception as e:
            logger.error("Error batch retrieving user votes: %s", e)
            return {}
