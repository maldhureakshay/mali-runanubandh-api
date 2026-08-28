"""
Comment Repository module.

Responsible for database operations on Comments collection.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Tuple

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.community.models.comment import Comment
from app.community.repositories.base import BaseRepository
from app.community.repositories.exceptions import DocumentNotFoundException, RepositoryException

logger = logging.getLogger(__name__)


class CommentRepository(BaseRepository):
    """
    Handles database operations for Comments.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """
        Initializes the repository with the comments collection name.
        """
        super().__init__(db, "comments")

    async def create_comment(self, comment: Comment) -> Comment:
        """
        Insert a new comment.
        """
        comment_data = comment.model_dump(by_alias=True, exclude={"id"})
        if comment.id:
            comment_data["_id"] = ObjectId(comment.id)
            
        created = await self.create(comment_data)
        return Comment.model_validate(created)

    async def get_comment(self, comment_id: str) -> Comment:
        """
        Fetch a comment by ID. Throws DocumentNotFoundException if missing or soft deleted.
        """
        doc = await self.find_by_id(comment_id)
        if doc.get("deletedAt") is not None:
            raise DocumentNotFoundException("Comment has been deleted.")
        return Comment.model_validate(doc)

    async def update_comment(self, comment_id: str, new_text: str) -> Comment:
        """
        Update the text of a comment and mark it as edited.
        """
        if not ObjectId.is_valid(comment_id):
            raise DocumentNotFoundException(f"Invalid comment ID: {comment_id}")
            
        current_time = datetime.now(timezone.utc)
        try:
            result = await self.collection.find_one_and_update(
                {
                    "_id": ObjectId(comment_id),
                    "deletedAt": None
                },
                {
                    "$set": {
                        "comment": new_text,
                        "edited": True,
                        "updatedAt": current_time
                    }
                },
                return_document=True
            )
            if not result:
                raise DocumentNotFoundException()
            return Comment.model_validate(result)
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error updating comment %s: %s", comment_id, e)
            raise RepositoryException(message=f"Database update error: {e}")

    async def delete_comment(self, comment_id: str) -> Comment:
        """
        Soft delete a comment by setting deletedAt to current UTC timestamp.
        """
        if not ObjectId.is_valid(comment_id):
            raise DocumentNotFoundException(f"Invalid comment ID: {comment_id}")
            
        current_time = datetime.now(timezone.utc)
        try:
            result = await self.collection.find_one_and_update(
                {
                    "_id": ObjectId(comment_id),
                    "deletedAt": None
                },
                {
                    "$set": {
                        "deletedAt": current_time,
                        "updatedAt": current_time
                    }
                },
                return_document=True
            )
            if not result:
                raise DocumentNotFoundException()
            return Comment.model_validate(result)
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error soft-deleting comment %s: %s", comment_id, e)
            raise RepositoryException(message=f"Database delete error: {e}")

    async def find_by_post(
        self,
        post_id: str,
        limit: int = 20,
        cursor: str | None = None
    ) -> Tuple[List[Comment], str | None]:
        """
        Find comments on a post, sorted chronologically (createdAt ascending).
        """
        # Fetch only active (non-soft-deleted) comments
        filters = {
            "postId": post_id,
            "deletedAt": None
        }
        sort = [("createdAt", 1), ("_id", 1)]
        
        docs, next_cursor = await self.find_many(filters, sort=sort, limit=limit, cursor=cursor)
        comments = [Comment.model_validate(doc) for doc in docs]
        return comments, next_cursor

    async def count_by_post(self, post_id: str) -> int:
        """
        Get total active comments count for a post.
        """
        return await self.count({
            "postId": post_id,
            "deletedAt": None
        })
