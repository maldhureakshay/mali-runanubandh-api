import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    DatabaseManager handles the lifecycles, configuration, and index initialization
    for the asynchronous MongoDB connection pool.
    """
    def __init__(self):
        self.client: AsyncIOMotorClient = None
        self.db = None

    def connect(self) -> None:
        """
        Initializes the async motor client and selects the target database.
        """
        logger.info(f"Initializing MongoDB client with URI: {settings.MONGO_URI}")
        self.client = AsyncIOMotorClient(
            settings.MONGO_URI,
            # Motor pool sizing defaults
            maxPoolSize=100,
            minPoolSize=10
        )
        self.db = self.client[settings.MONGO_DB_NAME]

    def disconnect(self) -> None:
        """
        Closes the active MongoDB connection pool.
        """
        if self.client:
            logger.info("Closing MongoDB client connections...")
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB client disconnected.")

    async def check_health(self) -> bool:
        """
        Validates connection health by executing a ping command.
        """
        if self.db is None:
            return False
        try:
            # The ping command is cheap and checks network/auth validity
            await self.db.command("ping")
            return True
        except PyMongoError as e:
            logger.error(f"MongoDB health check failed: {e}")
            return False

    async def ensure_indexes(self) -> None:
        """
        Creates the necessary spatial indexing for geoNear queries to work.
        Requires a 2dsphere index on the '_geoloc' field.
        """
        if self.db is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        
        collection = self.db[settings.MONGO_COLLECTION_NAME]
        
        try:
            logger.info(f"Ensuring 2dsphere index on collection '{settings.MONGO_COLLECTION_NAME}' for field '_geoloc'")
            # Create a 2dsphere spatial index on the '_geoloc' field
            index_name = await collection.create_index(
                [("_geoloc", "2dsphere")],
                name="geoloc_2dsphere_idx",
                background=True
            )
            logger.info(f"Geospatial index ready: {index_name}")
            
            # Ensure unique index on likes collection
            likes_collection = self.db["likes"]
            likes_index_name = await likes_collection.create_index(
                [("postId", 1), ("userId", 1)],
                name="likes_post_user_uidx",
                unique=True,
                background=True
            )
            logger.info(f"Likes compound index ready: {likes_index_name}")

            # Ensure unique indexes on poll_votes collection
            votes_collection = self.db["poll_votes"]
            
            # Index 1: Single-choice (postId + userId unique)
            vote_single_idx = await votes_collection.create_index(
                [("postId", 1), ("userId", 1)],
                name="poll_votes_single_uidx",
                unique=True,
                partialFilterExpression={"allowMultipleSelection": False},
                background=True
            )
            logger.info(f"Poll single-choice index ready: {vote_single_idx}")
            
            # Index 2: Multiple-choice (postId + userId + optionId unique)
            vote_multi_idx = await votes_collection.create_index(
                [("postId", 1), ("userId", 1), ("optionId", 1)],
                name="poll_votes_multi_uidx",
                unique=True,
                partialFilterExpression={"allowMultipleSelection": True},
                background=True
            )
            logger.info(f"Poll multi-choice index ready: {vote_multi_idx}")

            # Ensure indexes on reports collection
            reports_collection = self.db["reports"]
            await reports_collection.create_index([("postId", 1)], name="reports_post_id_idx", background=True)
            await reports_collection.create_index([("reportedBy", 1)], name="reports_reported_by_idx", background=True)
            await reports_collection.create_index([("status", 1), ("createdAt", 1)], name="reports_status_created_idx", background=True)
            await reports_collection.create_index(
                [("postId", 1), ("reportedBy", 1)],
                name="reports_post_reporter_uidx",
                unique=True,
                background=True
            )
            logger.info("Reports collection indexes successfully verified.")

            # Ensure indexes on notifications collection
            notifications_collection = self.db["notifications"]
            await notifications_collection.create_index(
                [("recipientUserId", 1), ("createdAt", -1)],
                name="notifications_recipient_created_idx",
                background=True
            )
            await notifications_collection.create_index(
                [("recipientUserId", 1), ("read", 1)],
                name="notifications_recipient_read_idx",
                background=True
            )
            logger.info("Notifications collection indexes successfully verified.")

            # Ensure indexes on posts collection
            posts_collection = self.db["posts"]
            try:
                await posts_collection.drop_index("posts_feed_idx")
            except PyMongoError:
                pass
                
            await posts_collection.create_index(
                [("moderation.status", 1), ("visibility.visibility", 1), ("isPinned", -1), ("publishedAt", -1)],
                name="posts_feed_v2_idx",
                background=True
            )
            await posts_collection.create_index(
                [("expiresAt", 1)],
                name="posts_expires_idx",
                background=True
            )
            
            try:
                await posts_collection.drop_index("posts_type_status_pub_idx")
            except PyMongoError:
                pass
                
            await posts_collection.create_index(
                [("type", 1), ("moderation.status", 1), ("isPinned", -1), ("publishedAt", -1)],
                name="posts_type_status_pub_v2_idx",
                background=True
            )
            logger.info("Posts collection indexes successfully verified.")
        except PyMongoError as e:
            logger.error(f"Error creating database indexes: {e}")
            raise e

    def get_collection(self):
        """
        Helper method to retrieve the target profiles collection object.
        """
        if self.db is None:
            raise RuntimeError("Database is not initialized.")
        return self.db[settings.MONGO_COLLECTION_NAME]

# Exported singleton instance
db_manager = DatabaseManager()
