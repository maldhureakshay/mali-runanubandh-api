"""
Database management module.

Handles lifecycle management, connection pools, and health checks for MongoDB
using the asynchronous Motor driver.
"""

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from app.core.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    DatabaseManager encapsulates the AsyncIOMotorClient and manages MongoDB connections.
    """

    def __init__(self) -> None:
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None

    def connect(self) -> None:
        """
        Initialize the MongoDB client connection pool and set the active database.
        """
        if self.client is not None:
            logger.warning("MongoDB client is already connected.")
            return

        logger.info("Connecting to MongoDB URI: %s", settings.MONGO_URI)
        try:
            self.client = AsyncIOMotorClient(
                settings.MONGO_URI,
                maxPoolSize=100,
                minPoolSize=10,
                tz_aware=True
            )
            self.db = self.client[settings.MONGO_DB_NAME]
            logger.info("Connected to database: %s", settings.MONGO_DB_NAME)
        except Exception as e:
            logger.error("Failed to connect to MongoDB: %s", e)
            raise e

    def disconnect(self) -> None:
        """
        Close active database connection pool.
        """
        if self.client:
            logger.info("Closing MongoDB connection pool...")
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB connection pool closed.")
        else:
            logger.warning("Attempted to disconnect MongoDB, but no client was active.")

    async def check_health(self) -> bool:
        """
        Perform a ping check to verify if MongoDB is active and accepting connections.
        
        Returns:
            bool: True if connection is healthy, False otherwise.
        """
        if self.db is None:
            logger.error("MongoDB check_health invoked but database is not initialized.")
            return False
        try:
            # Low-overhead ping to verify server status
            await self.db.command("ping")
            return True
        except PyMongoError as e:
            logger.error("MongoDB health check failed with PyMongoError: %s", e)
            return False
        except Exception as e:
            logger.error("MongoDB health check failed with unexpected error: %s", e)
            return False

    def get_database(self) -> AsyncIOMotorDatabase:
        """
        Retrieve database instance.
        
        Raises:
            RuntimeError: If connect() has not been called or database is unitialized.
        """
        if self.db is None:
            raise RuntimeError("Database not initialized. Please call connect() first.")
        return self.db


# Export singleton instance
db_manager = DatabaseManager()
