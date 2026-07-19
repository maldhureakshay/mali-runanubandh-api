import logging
from typing import Optional
from database import db_manager
from models.user import UserBase
from models.common import PaginatedResponse

from config import settings

logger = logging.getLogger(__name__)

class UserService:
    """
    UserService handles business logic and MongoDB queries for the users collection.
    """

    async def get_dashboard_metrics(self) -> dict:
        """
        Retrieves total/active counts for both users and profiles.
        """
        if db_manager.db is None:
            raise RuntimeError("Database is not initialized.")

        users_col = db_manager.db["users"]
        profiles_col = db_manager.db[settings.MONGO_COLLECTION_NAME]

        # Use count_documents for efficiency
        total_users = await users_col.count_documents({})
        active_users = await users_col.count_documents({"status": True})
        
        total_profiles = await profiles_col.count_documents({})
        active_profiles = await profiles_col.count_documents({"active": True})

        return {
            "totalUsers": total_users,
            "activeUsers": active_users,
            "totalProfiles": total_profiles,
            "activeProfiles": active_profiles
        }

    async def find_users(
        self,
        page: int = 1,
        limit: int = 10,
        phone: Optional[str] = None
    ) -> PaginatedResponse[UserBase]:
        """
        Retrieves users from the 'users' collection with pagination and optional search filter.
        Results are ordered by 'createdAt' descending (latest first).
        """
        if db_manager.db is None:
            raise RuntimeError("Database is not initialized.")

        collection = db_manager.db["users"]
        skip = (page - 1) * limit

        query_filter = {}
        if phone:
            # Match phone number contains the search string
            query_filter["phoneNumber"] = {"$regex": phone, "$options": "i"}

        # Build aggregation pipeline to query total and data in one step
        pipeline = [
            {"$match": query_filter},
            # Sort by createdAt descending, if not present sort by _id descending
            {"$sort": {"createdAt": -1, "_id": -1}},
            {
                "$facet": {
                    "metadata": [{"$count": "total"}],
                    "data": [
                        {"$skip": skip},
                        {"$limit": limit}
                    ]
                }
            }
        ]

        logger.info(
            f"Executing user search with query_filter={query_filter}, "
            f"page={page}, limit={limit}"
        )

        try:
            cursor = collection.aggregate(pipeline)
            results = await cursor.to_list(length=1)

            if not results:
                return PaginatedResponse(data=[], total=0, page=page, limit=limit, has_more=False)

            facet_result = results[0]
            metadata = facet_result.get("metadata", [])
            data_list = facet_result.get("data", [])
            total = metadata[0]["total"] if metadata else 0

            users = [UserBase.model_validate(doc) for doc in data_list]
            has_more = total > (skip + len(users))

            return PaginatedResponse(
                data=users,
                total=total,
                page=page,
                limit=limit,
                has_more=has_more
            )
        except Exception as e:
            logger.error(f"Error executing user search: {e}")
            raise

# Exported singleton instance
user_service = UserService()

