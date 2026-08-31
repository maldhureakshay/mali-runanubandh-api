from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.community.repositories.base import BaseRepository
from app.community.models.statistics import CommunityStatisticsDB

class StatisticsRepository(BaseRepository):
    """
    Repository for managing community statistics.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, "community_statistics")
        
    async def get_statistics(self) -> Optional[CommunityStatisticsDB]:
        """
        Retrieve the global statistics document.
        """
        doc = await self.collection.find_one({"_id": "global_stats"})
        if doc:
            return CommunityStatisticsDB(**doc)
        return None
        
    async def upsert_statistics(self, stats: CommunityStatisticsDB) -> CommunityStatisticsDB:
        """
        Upsert the global statistics document.
        """
        doc = stats.model_dump(by_alias=True)
        await self.collection.update_one(
            {"_id": "global_stats"},
            {"$set": doc},
            upsert=True
        )
        return stats
