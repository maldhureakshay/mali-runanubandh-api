"""
Post Repository module.

Responsible for handling database operations for Community Posts, utilizing MongoDB atomic operators
and returning Pydantic models.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Tuple

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.community.enums import PostStatus, PostType, Visibility
from app.community.models.post import Post
from app.community.repositories.base import BaseRepository
from app.community.repositories.exceptions import DocumentNotFoundException

logger = logging.getLogger(__name__)


class PostRepository(BaseRepository):
    """
    Handles database operations for Community Posts.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """
        Initializes the repository with the database client and posts collection name.
        """
        super().__init__(db, "posts")

    async def create_post(self, post: Post) -> Post:
        """
        Insert a new post into the database.
        """
        # Convert Pydantic model to dict, excluding None/unset _id to let Mongo generate it
        post_data = post.model_dump(by_alias=True, exclude={"id"})
        if post.id:
            post_data["_id"] = ObjectId(post.id) if ObjectId.is_valid(post.id) else post.id
            
        created_data = await self.create(post_data)
        return Post.model_validate(created_data)


    async def get_post(self, post_id: str) -> Post:
        """
        Fetch a single post by ID.
        """
        doc = await self.find_by_id(post_id)
        return Post.model_validate(doc)

    async def update_post(self, post_id: str, update_data: Dict[str, Any]) -> Post:
        """
        Update a post's content or settings.
        """
        # Make sure we don't accidentally override system fields or _id
        update_data.pop("_id", None)
        update_data["updatedAt"] = datetime.now(timezone.utc)
        
        doc = await self.update(post_id, update_data)
        return Post.model_validate(doc)

    async def delete_post(self, post_id: str) -> bool:
        """
        Soft delete a post by setting status to DELETED and updating timestamp.
        """
        await self.soft_delete(post_id)
        return True

    async def publish_post(self, post_id: str) -> Post:
        """
        Publish a post, marking its status as APPROVED and setting the publishedAt timestamp.
        """
        current_time = datetime.now(timezone.utc)
        update_query = {
            "moderation.status": PostStatus.APPROVED.value,
            "publishedAt": current_time,
            "updatedAt": current_time
        }
        doc = await self.update(post_id, update_query)
        return Post.model_validate(doc)

    async def approve_post(self, post_id: str, admin_id: str, approval_notes: str | None = None) -> Post:
        """
        Approve a post by moderator. Sets status to APPROVED and sets publishedAt timestamp.
        """
        current_time = datetime.now(timezone.utc)
        update_query = {
            "moderation.status": PostStatus.APPROVED.value,
            "moderation.reviewedBy": admin_id,
            "moderation.reviewedAt": current_time,
            "publishedAt": current_time,
            "updatedAt": current_time
        }
        if approval_notes:
            update_query["moderation.approvalNotes"] = approval_notes

        doc = await self.update(post_id, update_query)
        return Post.model_validate(doc)

    async def request_changes(
        self,
        post_id: str,
        admin_id: str,
        review_comments: str,
        rejection_reason: str | None = None
    ) -> Post:
        """
        Set a post's status to NEEDS_CHANGES with review feedback.
        """
        current_time = datetime.now(timezone.utc)
        update_query = {
            "moderation.status": PostStatus.NEEDS_CHANGES.value,
            "moderation.reviewedBy": admin_id,
            "moderation.reviewedAt": current_time,
            "moderation.reviewComments": review_comments,
            "updatedAt": current_time
        }
        if rejection_reason:
            update_query["moderation.rejectionReason"] = rejection_reason
            
        doc = await self.update(post_id, update_query)
        return Post.model_validate(doc)

    async def reject_post(self, post_id: str, admin_id: str, reason: str) -> Post:
        """
        Reject a post by moderator. Sets status to NEEDS_CHANGES.
        """
        current_time = datetime.now(timezone.utc)
        update_query = {
            "moderation.status": PostStatus.NEEDS_CHANGES.value,
            "moderation.reviewedBy": admin_id,
            "moderation.reviewedAt": current_time,
            "moderation.rejectionReason": reason,
            "updatedAt": current_time
        }
        doc = await self.update(post_id, update_query)
        return Post.model_validate(doc)

    async def submit_post(self, post_id: str, is_resubmission: bool = False) -> Post:
        """
        Submit a draft or needs_changes post for review. 
        Records submittedAt, or resubmittedAt and increments version if resubmitting.
        """
        query_id = ObjectId(post_id) if ObjectId.is_valid(post_id) else post_id
            
        current_time = datetime.now(timezone.utc)
        
        if is_resubmission:
            update_cmd = {
                "$set": {
                    "moderation.status": PostStatus.PENDING_REVIEW.value,
                    "moderation.resubmittedAt": current_time,
                    "updatedAt": current_time
                },
                "$inc": {
                    "moderation.version": 1
                },
                "$unset": {
                    "moderation.reviewComments": "",
                    "moderation.rejectionReason": ""
                }
            }
            doc = await self.collection.find_one_and_update(
                {"_id": query_id},
                update_cmd,
                return_document=True
            )
            if not doc:
                raise DocumentNotFoundException()
        else:
            update_query = {
                "moderation.status": PostStatus.PENDING_REVIEW.value,
                "moderation.submittedAt": current_time,
                "updatedAt": current_time
            }
            doc = await self.update(post_id, update_query)
            
        return Post.model_validate(doc)

    async def _increment_statistic_counter(self, post_id: str, field_name: str, amount: int) -> Post:
        """
        Helper method to atomically increment or decrement post statistics.
        """
        query_id = ObjectId(post_id) if ObjectId.is_valid(post_id) else post_id
            
        current_time = datetime.now(timezone.utc)
        # Ensure counter does not go below zero when decrementing
        if amount < 0:
            # Conditional atomic decrement if count > 0 is handled via MongoDB update query matching
            result = await self.collection.find_one_and_update(
                {
                    "_id": query_id,
                    f"statistics.{field_name}": {"$gt": 0}
                },
                {
                    "$inc": {f"statistics.{field_name}": amount},
                    "$set": {"updatedAt": current_time}
                },
                return_document=True
            )
            if not result:
                # If it didn't match gt 0, just execute a set to 0 or return current state
                result = await self.collection.find_one_and_update(
                    {"_id": query_id},
                    {
                        "$set": {
                            f"statistics.{field_name}": 0,
                            "updatedAt": current_time
                        }
                    },
                    return_document=True
                )
        else:
            result = await self.collection.find_one_and_update(
                {"_id": query_id},
                {
                    "$inc": {f"statistics.{field_name}": amount},
                    "$set": {"updatedAt": current_time}
                },
                return_document=True
            )

        if not result:
            raise DocumentNotFoundException(f"Post {post_id} not found.")
            
        return Post.model_validate(result)

    async def increment_views(self, post_id: str) -> Post:
        """
        Atomically increment post view count.
        """
        return await self._increment_statistic_counter(post_id, "viewsCount", 1)

    async def increment_likes(self, post_id: str) -> Post:
        """
        Atomically increment post like count.
        """
        return await self._increment_statistic_counter(post_id, "likesCount", 1)

    async def decrement_likes(self, post_id: str) -> Post:
        """
        Atomically decrement post like count.
        """
        return await self._increment_statistic_counter(post_id, "likesCount", -1)

    async def increment_comments(self, post_id: str) -> Post:
        """
        Atomically increment post comment count.
        """
        return await self._increment_statistic_counter(post_id, "commentsCount", 1)

    async def decrement_comments(self, post_id: str) -> Post:
        """
        Atomically decrement post comment count.
        """
        return await self._increment_statistic_counter(post_id, "commentsCount", -1)

    async def increment_reports(self, post_id: str) -> Post:
        """
        Atomically increment post report count.
        """
        return await self._increment_statistic_counter(post_id, "reportsCount", 1)

    async def find_feed(
        self,
        visibility: Visibility = Visibility.PUBLIC,
        limit: int = 20,
        cursor: str | None = None
    ) -> Tuple[List[Post], str | None]:
        """
        Retrieve published posts feed matching visibility, sorted by publishedAt descending.
        """
        now = datetime.now(timezone.utc)
        filters = {
            "moderation.status": PostStatus.APPROVED.value,
            "visibility.visibility": visibility.value,
            "$and": [
                {
                    "$or": [
                        {"metadata.expiresAt": None},
                        {"metadata.expiresAt": {"$gt": now}},
                        {"metadata.expiresAt": {"$exists": False}}
                    ]
                },
                {
                    "$or": [
                        {"expiresAt": None},
                        {"expiresAt": {"$gt": now}},
                        {"expiresAt": {"$exists": False}}
                    ]
                }
            ]
        }
        sort = [("isPinned", -1), ("publishedAt", -1), ("_id", -1)]
        
        docs, next_cursor = await self.find_many(filters, sort=sort, limit=limit, cursor=cursor)
        posts = []
        for doc in docs:
            try:
                posts.append(Post.model_validate(doc))
            except Exception as e:
                logger.error(f"Failed to validate post {doc.get('_id')}: {e}")

        return posts, next_cursor

    async def find_posts_by_author(
        self,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
        status: PostStatus | None = None
    ) -> Tuple[List[Post], str | None]:
        """
        Retrieve posts authored by a specific user, sorted by createdAt descending.
        Optionally filter by a specific status.
        """
        filters: Dict[str, Any] = {
            "author.userId": user_id
        }
        
        if status:
            filters["moderation.status"] = status.value
        else:
            # Shows draft/pending/approved, but hides deleted
            filters["moderation.status"] = {"$ne": PostStatus.DELETED.value}

        sort = [("createdAt", -1), ("_id", -1)]
        
        docs, next_cursor = await self.find_many(filters, sort=sort, limit=limit, cursor=cursor)
        posts = []
        for doc in docs:
            try:
                posts.append(Post.model_validate(doc))
            except Exception as e:
                logger.error(f"Failed to validate post {doc.get('_id')}: {e}")
        return posts, next_cursor

    async def find_posts_by_type(
        self,
        post_type: PostType,
        limit: int = 20,
        cursor: str | None = None
    ) -> Tuple[List[Post], str | None]:
        """
        Retrieve approved posts filtered by PostType, sorted by publishedAt descending.
        """
        now = datetime.now(timezone.utc)
        filters = {
            "type": post_type.value,
            "moderation.status": PostStatus.APPROVED.value,
            "$and": [
                {
                    "$or": [
                        {"metadata.expiresAt": None},
                        {"metadata.expiresAt": {"$gt": now}},
                        {"metadata.expiresAt": {"$exists": False}}
                    ]
                },
                {
                    "$or": [
                        {"expiresAt": None},
                        {"expiresAt": {"$gt": now}},
                        {"expiresAt": {"$exists": False}}
                    ]
                }
            ]
        }
        sort = [("isPinned", -1), ("publishedAt", -1), ("_id", -1)]
        
        docs, next_cursor = await self.find_many(filters, sort=sort, limit=limit, cursor=cursor)
        posts = []
        for doc in docs:
            try:
                posts.append(Post.model_validate(doc))
            except Exception as e:
                logger.error(f"Failed to validate post {doc.get('_id')}: {e}")
        return posts, next_cursor

    async def increment_poll_option_votes(self, post_id: str, option_ids: List[str]) -> Post:
        """
        Atomically increment the votesCount for specific optionIds inside the metadata.options list.
        """
        query_id = ObjectId(post_id) if ObjectId.is_valid(post_id) else post_id
            
        current_time = datetime.now(timezone.utc)
        
        try:
            result = await self.collection.find_one_and_update(
                {"_id": query_id},
                {
                    "$inc": {"metadata.options.$[elem].votesCount": 1},
                    "$set": {"updatedAt": current_time}
                },
                array_filters=[{"elem.id": {"$in": option_ids}}],
                return_document=True
            )
            if not result:
                raise DocumentNotFoundException(f"Post {post_id} not found.")
            return Post.model_validate(result)
        except Exception as e:
            logger.error("Error incrementing poll votes: %s", e)
            raise RepositoryException(message=f"Database update error: {e}")

    async def decrement_poll_option_votes(self, post_id: str, option_ids: List[str]) -> Post:
        """
        Atomically decrement the votesCount for specific optionIds inside the metadata.options list.
        """
        query_id = ObjectId(post_id) if ObjectId.is_valid(post_id) else post_id
            
        current_time = datetime.now(timezone.utc)
        
        try:
            result = await self.collection.find_one_and_update(
                {"_id": query_id},
                {
                    "$inc": {"metadata.options.$[elem].votesCount": -1},
                    "$set": {"updatedAt": current_time}
                },
                array_filters=[{"elem.id": {"$in": option_ids}}],
                return_document=True
            )
            if not result:
                raise DocumentNotFoundException(f"Post {post_id} not found.")
            return Post.model_validate(result)
        except Exception as e:
            logger.error("Error decrementing poll votes: %s", e)
            raise RepositoryException(message=f"Database update error: {e}")

    async def restore_post(self, post_id: str, admin_id: str) -> Post:
        """
        Restore a deleted or rejected post, resetting status to APPROVED and unsetting deletedAt.
        """
        query_id = ObjectId(post_id) if ObjectId.is_valid(post_id) else post_id
            
        current_time = datetime.now(timezone.utc)
        try:
            result = await self.collection.find_one_and_update(
                {"_id": query_id},
                {
                    "$set": {
                        "moderation.status": PostStatus.APPROVED.value,
                        "moderation.reviewedBy": admin_id,
                        "moderation.reviewedAt": current_time,
                        "updatedAt": current_time
                    },
                    "$unset": {
                        "deletedAt": ""
                    }
                },
                return_document=True
            )
            if not result:
                raise DocumentNotFoundException(f"Post {post_id} not found.")
            return Post.model_validate(result)
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error restoring post %s: %s", post_id, e)
            raise RepositoryException(message=f"Database update error: {e}")

    async def find_pending_posts(
        self,
        post_type: PostType | None = None,
        author_name: str | None = None,
        author_id: str | None = None,
        submission_date: str | None = None,
        sort_order: int = -1,
        limit: int = 20,
        cursor: str | None = None
    ) -> Tuple[List[Post], str | None]:
        """
        Retrieve pending posts for moderation queue with filters and pagination.
        """
        filters: Dict[str, Any] = {
            "moderation.status": PostStatus.PENDING_REVIEW.value
        }
        
        if post_type:
            filters["type"] = post_type.value
            
        if author_id:
            filters["author.userId"] = author_id
            
        if author_name:
            # Case-insensitive partial match
            filters["author.fullName"] = {"$regex": author_name, "$options": "i"}
            
        if submission_date:
            # Basic date string prefix matching or range could be implemented here
            # Assuming submission_date is 'YYYY-MM-DD'
            try:
                start_date = datetime.strptime(submission_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                end_date = datetime.strptime(submission_date + " 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                filters["moderation.submittedAt"] = {"$gte": start_date, "$lte": end_date}
            except ValueError:
                logger.warning(f"Invalid submission_date format: {submission_date}")
                
        # Sort by submittedAt. sort_order: -1 for newest first, 1 for oldest first
        sort = [("moderation.submittedAt", sort_order), ("_id", sort_order)]
        
        docs, next_cursor = await self.find_many(filters, sort=sort, limit=limit, cursor=cursor)
        posts = []
        for doc in docs:
            try:
                posts.append(Post.model_validate(doc))
            except Exception as e:
                logger.error(f"Failed to validate post {doc.get('_id')}: {e}")
        return posts, next_cursor

    async def find_posts_by_admin(
        self,
        post_type: PostType,
        statuses: List[PostStatus] | None = None,
        announcement_type: str | None = None,
        active: bool | None = None,
        created_date: str | None = None,
        limit: int = 20,
        cursor: str | None = None
    ) -> Tuple[List[Post], str | None]:
        """
        Retrieve posts for admin management, filtered by type and optional criteria.

        Args:
            post_type: The PostType to list (e.g. MARRIAGE_SUCCESS).
            statuses: Optional list of PostStatus values to filter by. Defaults to all non-DELETED.
            announcement_type: Optional metadata.announcementType string (SINGLE_PERSON / COUPLE).
            active: If True, only non-expired posts (expiresAt > now or absent).
                    If False, only expired posts (expiresAt <= now).
                    If None, no expiry filter applied.
            created_date: Optional date string 'YYYY-MM-DD' to filter by createdAt day.
            limit: Max results per page.
            cursor: Opaque cursor for next page.
        """
        now = datetime.now(timezone.utc)

        filters: Dict[str, Any] = {
            "type": post_type.value,
        }

        # Status filter
        if statuses:
            filters["moderation.status"] = {"$in": [s.value for s in statuses]}
        else:
            # Default: exclude physically-deleted posts only
            filters["moderation.status"] = {"$ne": PostStatus.DELETED.value}

        # announcementType filter (stored in metadata subdoc)
        if announcement_type:
            filters["metadata.announcementType"] = announcement_type

        # Active / expired filter based on root-level expiresAt
        if active is True:
            # Active: expiresAt missing/null OR expiresAt > now
            filters["$or"] = [
                {"expiresAt": {"$exists": False}},
                {"expiresAt": None},
                {"expiresAt": {"$gt": now}},
            ]
        elif active is False:
            # Expired: expiresAt exists AND expiresAt <= now
            filters["expiresAt"] = {"$exists": True, "$ne": None, "$lte": now}

        # Created-date filter (full UTC day range)
        if created_date:
            try:
                day_start = datetime.strptime(created_date, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                day_end = day_start.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
                filters["createdAt"] = {"$gte": day_start, "$lte": day_end}
            except ValueError:
                logger.warning("find_posts_by_admin: invalid created_date format: %s", created_date)

        sort = [("createdAt", -1), ("_id", -1)]

        docs, next_cursor = await self.find_many(
            filters, sort=sort, limit=limit, cursor=cursor
        )
        posts = []
        for doc in docs:
            try:
                posts.append(Post.model_validate(doc))
            except Exception as e:
                logger.error("Failed to validate post %s in admin listing: %s", doc.get("_id"), e)
        return posts, next_cursor

    async def get_post_for_review(self, post_id: str) -> Post:
        """
        Retrieve a specific post strictly for moderation review.
        """
        doc = await self.find_by_id(post_id)
        if doc.get("moderation", {}).get("status") != PostStatus.PENDING_REVIEW.value:
            # We don't raise PostNotFound here, just return it so service can decide.
            pass
        return Post.model_validate(doc)
