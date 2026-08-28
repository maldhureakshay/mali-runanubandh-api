#!/usr/bin/env python
import asyncio
import logging
import sys
import os

# Add the parent directory to the sys path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db_manager
from app.core.database import db_manager as community_db_manager
from app.community.repositories.post import PostRepository
from app.community.services.birthday import BirthdayPostService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing database connections...")
    db_manager.connect()
    community_db_manager.connect()
    
    try:
        post_repo = PostRepository(community_db_manager.db)
        birthday_service = BirthdayPostService(post_repo)
        
        logger.info("Starting birthday post generation...")
        created_count = await birthday_service.generate_birthday_posts()
        logger.info(f"Successfully generated {created_count} birthday posts.")
    except Exception as e:
        logger.error(f"Error generating birthday posts: {e}", exc_info=True)
    finally:
        logger.info("Closing database connections...")
        db_manager.disconnect()
        community_db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
