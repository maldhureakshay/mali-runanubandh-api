"""
Base Repository module.

Provides a reusable generic BaseRepository class implementing common asynchronous
CRUD operations interfacing with MongoDB via Motor, including cursor-based pagination.
"""

import base64
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Tuple
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection

from app.community.repositories.exceptions import (
    DocumentNotFoundException,
    InvalidCursorException,
    RepositoryException,
)
from app.community.enums import PostStatus

logger = logging.getLogger(__name__)


class BaseRepository:
    """
    Abstract/base repository supplying default data access utilities for MongoDB collections.
    """

    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str) -> None:
        """
        Initialize the repository.
        """
        self.db = db
        self.collection: AsyncIOMotorCollection = db[collection_name]

    @staticmethod
    def encode_cursor(last_id: str, last_sort_value: Any = None) -> str:
        """
        Serialize pagination details into a base64 encoded cursor string.
        """
        data = {"last_id": last_id}
        if last_sort_value is not None:
            if isinstance(last_sort_value, datetime):
                # Ensure UTC isoformat
                data["last_sort_value"] = last_sort_value.replace(tzinfo=timezone.utc).isoformat()
            else:
                data["last_sort_value"] = last_sort_value
        json_str = json.dumps(data)
        return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decode_cursor(cursor_str: str) -> Dict[str, Any]:
        """
        Deserialize a base64 cursor string into field value dictionary.
        """
        try:
            decoded_bytes = base64.b64decode(cursor_str.encode("utf-8"))
            return json.loads(decoded_bytes.decode("utf-8"))
        except Exception as e:
            logger.error("Failed to decode cursor: %s", e)
            raise InvalidCursorException()

    async def create(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert a new document.
        """
        try:
            result = await self.collection.insert_one(document)
            document["_id"] = result.inserted_id
            return document
        except Exception as e:
            logger.error("Error creating document in collection %s: %s", self.collection.name, e)
            raise RepositoryException(message=f"Database write error: {e}")

    async def find_by_id(self, doc_id: str) -> Dict[str, Any]:
        """
        Retrieve a single document by its hex string ObjectId identifier or string key.
        """
        query_id = ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id
        try:
            doc = await self.collection.find_one({"_id": query_id})
            if not doc:
                raise DocumentNotFoundException()
            return doc
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error fetching doc %s from %s: %s", doc_id, self.collection.name, e)
            raise RepositoryException(message=f"Database query error: {e}")

    async def find_one(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve a single document matching the given filters.
        """
        try:
            doc = await self.collection.find_one(filters)
            if not doc:
                raise DocumentNotFoundException()
            return doc
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error fetching single doc from %s: %s", self.collection.name, e)
            raise RepositoryException(message=f"Database query error: {e}")

    async def find_many(
        self,
        filters: Dict[str, Any],
        sort: List[Tuple[str, int]] | None = None,
        limit: int = 20,
        cursor: str | None = None
    ) -> Tuple[List[Dict[str, Any]], str | None]:
        """
        Retrieve multiple documents using cursor-based pagination.
        """
        try:
            query = dict(filters)
            
            # Apply cursor pagination if cursor is provided
            if cursor:
                cursor_data = self.decode_cursor(cursor)
                last_id = cursor_data.get("last_id")
                last_sort_value = cursor_data.get("last_sort_value")
                
                # Default sorting is by _id if not specified
                effective_sort = sort or [("_id", -1)]
                sort_field, sort_dir = effective_sort[0]
                
                last_id_val = ObjectId(last_id) if ObjectId.is_valid(last_id) else last_id
                if sort_field == "_id":
                    if sort_dir == -1:
                        query["_id"] = {"$lt": last_id_val}
                    else:
                        query["_id"] = {"$gt": last_id_val}
                else:
                    # Parse timestamp if the sort field is datetime
                    if last_sort_value and isinstance(last_sort_value, str):
                        try:
                            # Try parsing ISO timestamp
                            last_sort_value = datetime.fromisoformat(last_sort_value.replace("Z", "+00:00"))
                        except ValueError:
                            pass
                    
                    # Formulate the compound comparison query
                    if sort_dir == -1:
                        query["$or"] = [
                            {sort_field: {"$lt": last_sort_value}},
                            {sort_field: last_sort_value, "_id": {"$lt": last_id_val}}
                        ]
                    else:
                        query["$or"] = [
                            {sort_field: {"$gt": last_sort_value}},
                            {sort_field: last_sort_value, "_id": {"$gt": last_id_val}}
                        ]

            # Construct find cursor
            db_cursor = self.collection.find(query)
            if sort:
                db_cursor = db_cursor.sort(sort)
            else:
                db_cursor = db_cursor.sort("_id", -1) # Default descending ID order

            # Fetch limit + 1 to check if there is a next page
            docs = await db_cursor.limit(limit + 1).to_list(length=limit + 1)
            
            has_next = len(docs) > limit
            results = docs[:limit]
            
            next_cursor = None
            if has_next and results:
                last_item = results[-1]
                last_item_id = str(last_item["_id"])
                
                effective_sort = sort or [("_id", -1)]
                sort_field = effective_sort[0][0]
                
                if sort_field == "_id":
                    next_cursor = self.encode_cursor(last_item_id)
                else:
                    # Get value of the sort field
                    sort_val = last_item.get(sort_field)
                    next_cursor = self.encode_cursor(last_item_id, sort_val)
            
            return results, next_cursor
            
        except RepositoryException:
            raise
        except Exception as e:
            logger.error("Error fetching list of docs from %s: %s", self.collection.name, e)
            raise RepositoryException(message=f"Database query error: {e}")

    async def update(self, doc_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update fields of an existing document.
        """
        query_id = ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id
        try:
            result = await self.collection.find_one_and_update(
                {"_id": query_id},
                {"$set": update_data},
                return_document=True
            )
            if not result:
                raise DocumentNotFoundException()
            return result
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error updating doc %s in %s: %s", doc_id, self.collection.name, e)
            raise RepositoryException(message=f"Database update error: {e}")

    async def delete(self, doc_id: str) -> bool:
        """
        Remove a document physically from the collection.
        """
        query_id = ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id
        try:
            result = await self.collection.delete_one({"_id": query_id})
            if result.deleted_count == 0:
                raise DocumentNotFoundException()
            return True
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error deleting doc %s in %s: %s", doc_id, self.collection.name, e)
            raise RepositoryException(message=f"Database delete error: {e}")

    async def soft_delete(self, doc_id: str) -> Dict[str, Any]:
        """
        Perform a soft delete by setting status to DELETED and updated/deleted timestamps.
        """
        query_id = ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id
        try:
            current_time = datetime.now(timezone.utc)
            result = await self.collection.find_one_and_update(
                {"_id": query_id},
                {
                    "$set": {
                        "moderation.status": PostStatus.DELETED.value,
                        "updatedAt": current_time,
                        "deletedAt": current_time
                    }
                },
                return_document=True
            )
            if not result:
                raise DocumentNotFoundException()
            return result
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error soft-deleting doc %s in %s: %s", doc_id, self.collection.name, e)
            raise RepositoryException(message=f"Database soft delete error: {e}")

    async def count(self, filters: Dict[str, Any]) -> int:
        """
        Count documents matching the query filters.
        """
        try:
            return await self.collection.count_documents(filters)
        except Exception as e:
            logger.error("Error counting docs in %s: %s", self.collection.name, e)
            raise RepositoryException(message=f"Database query error: {e}")

    async def exists(self, filters: Dict[str, Any]) -> bool:
        """
        Check if any document matches the query filters.
        """
        try:
            count = await self.collection.count_documents(filters, limit=1)
            return count > 0
        except Exception as e:
            logger.error("Error checking document existence in %s: %s", self.collection.name, e)
            raise RepositoryException(message=f"Database query error: {e}")
