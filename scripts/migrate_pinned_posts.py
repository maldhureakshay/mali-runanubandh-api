import os
import sys
import asyncio
import logging

# Dynamically append the parent directory of this script to sys.path to allow imports from config
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def run_migration():
    """
    Connects to the AWS EC2 production MongoDB instance and backfills the `isPinned` 
    field for all existing community posts to fix the sorting order.
    """
    prod_uri = settings.PROD_MONGO_URI
    if not prod_uri or prod_uri.strip() == "":
        logger.critical(
            "\n❌ Error: PROD_MONGO_URI is not configured in your .env file!\n"
        )
        sys.exit(1)

    # Use the db name from config or parse from URI
    db_name = settings.MONGO_DB_NAME

    logger.info(f"Connecting to Production Database: {prod_uri.split('@')[-1] if '@' in prod_uri else prod_uri}")
    
    client = AsyncIOMotorClient(prod_uri)
    
    # Optional: fallback to extract DB name from the connected client if default 'matrimony' isn't right
    try:
        # motor requires await for ping
        await client.admin.command("ping")
        logger.info("Successfully connected to EC2 MongoDB!")
    except Exception as e:
        logger.critical(f"Connection failed: {e}")
        sys.exit(1)

    db = client[db_name]
    posts = db['posts']

    print("\n" + "="*60)
    print("🚨 WARNING: PRODUCTION DATABASE MIGRATION 🚨")
    print("="*60)
    print("This will backfill the `isPinned` field on existing posts.")
    confirm = input("Are you sure you want to proceed? [y/N]: ").strip().lower()
    if confirm not in ["y", "yes"]:
        logger.info("Migration cancelled by user.")
        client.close()
        sys.exit(0)

    # 1. Backfill TRUE for existing high priority announcements
    result_true = await posts.update_many(
        {'type': 'ANNOUNCEMENT', 'metadata.priority': 'HIGH'},
        {'$set': {'isPinned': True}}
    )
    logger.info(f"✅ Updated {result_true.modified_count} existing pinned posts with `isPinned=True`.")

    # 2. Backfill FALSE for all other posts where `isPinned` doesn't exist
    result_false = await posts.update_many(
        {'isPinned': {'$exists': False}},
        {'$set': {'isPinned': False}}
    )
    logger.info(f"✅ Updated {result_false.modified_count} other posts with `isPinned=False`.")

    print("\n" + "="*60)
    print("🎉 MIGRATION COMPLETED SUCCESSFULLY! 🎉")
    print("="*60 + "\n")

    client.close()

if __name__ == "__main__":
    asyncio.run(run_migration())
