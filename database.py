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
        except PyMongoError as e:
            logger.error(f"Error creating spatial index on MongoDB: {e}")
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
