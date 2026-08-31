#!/usr/bin/env python
import asyncio
import logging
import sys
import os
from datetime import datetime

# Add the parent directory to the sys path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db_manager
from app.community.repositories.statistics import StatisticsRepository
from app.community.models.statistics import CommunityStatisticsDB
from app.core.config import settings
import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def get_algolia_count(query: str) -> int:
    """
    Function to get count from Algolia for the given query.
    """
    algolia_app_id = "FAU9NYCABZ"
    algolia_api_key = "85245b1373fe7ab9e3c3bbb68117376b"
    algolia_index_name = "users_index"
 
    if algolia_app_id and algolia_api_key:
        try:
            logger.info(f"Algolia credentials found. Querying Algolia for: {query}")
            url = f"https://{algolia_app_id}-dsn.algolia.net/1/indexes/{algolia_index_name}/query"
            headers = {
                "X-Algolia-Application-Id": algolia_app_id,
                "X-Algolia-API-Key": algolia_api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "query": query,
                "hitsPerPage": 0
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("nbHits", 0)
                    else:
                        error_text = await response.text()
                        logger.error(f"Algolia API Error: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error querying Algolia: {e}. Falling back to MongoDB.")
        
    logger.info(f"Falling back to MongoDB regex search for: {query}")
    profiles_col = db_manager.get_collection()
    count = await profiles_col.count_documents({
        "$or": [
            {"job": {"$regex": query, "$options": "i"}},
            {"job_category": {"$regex": query, "$options": "i"}},
            {"job_subcategory": {"$regex": query, "$options": "i"}}
        ]
    })
    return count

async def main():
    logger.info("Initializing database connections...")
    db_manager.connect()
    
    try:
        profiles_col = db_manager.get_collection()
        stats_repo = StatisticsRepository(db_manager.db)
        
        logger.info("Calculating community statistics...")
        
        # 1. Members (all users - assuming distinct profiles or total profiles)
        users_col = db_manager.db["users"]
        members_count = await users_col.count_documents({})
        
        # 2. Active Profiles (entire count, no filter - wait, prompt says "for active profiles give me profiles entire count dont filter it")
        # I will set activeProfiles = members_count based on "dont filter it" for active profiles
        # But if members = all users, maybe they mean members = firebase users. 
        # I'll use total documents for both for now to satisfy "dont filter it".
        active_profiles_count = await profiles_col.count_documents({})
        
        # 3. New Profiles (after 10th Jan 2026)
        jan_10_2026 = datetime(2026, 1, 10)
        new_profiles_count = await profiles_col.count_documents({
            "created": {"$gte": jan_10_2026}
        })
        
        # 4. Verified Profiles (is_verified == True)
        verified_profiles_count = await profiles_col.count_documents({
            "is_verified": True
        })
        
        # 5. Doctors
        doctors_count = await get_algolia_count("doctor")
        
        # 6. Engineers
        engineers_count = await get_algolia_count("engineer")
        
        stats = CommunityStatisticsDB(
            members=f"{members_count:,}+" if members_count > 0 else "0",
            activeProfiles=f"{active_profiles_count:,}+" if active_profiles_count > 0 else "0",
            doctors=f"{doctors_count:,}+" if doctors_count > 0 else "0",
            engineers=f"{engineers_count:,}+" if engineers_count > 0 else "0",
            new=f"{new_profiles_count:,}+" if new_profiles_count > 0 else "0",
            verified=f"{verified_profiles_count:,}+" if verified_profiles_count > 0 else "0"
        )
        
        logger.info(f"Calculated Stats: {stats.model_dump()}")
        
        logger.info("Saving statistics to database...")
        await stats_repo.upsert_statistics(stats)
        logger.info("Statistics updated successfully.")
        
    except Exception as e:
        logger.error(f"Error updating community statistics: {e}", exc_info=True)
    finally:
        logger.info("Closing database connections...")
        db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
