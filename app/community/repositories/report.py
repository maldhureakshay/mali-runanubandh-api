"""
Report Repository module.

Responsible for database operations on Reports collection.
"""

from datetime import datetime, timezone
import logging
from typing import Any, List, Optional, Tuple

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.community.models.report import Report
from app.community.enums import ReportStatus
from app.community.repositories.base import BaseRepository
from app.community.repositories.exceptions import DocumentNotFoundException, RepositoryException

logger = logging.getLogger(__name__)


class ReportRepository(BaseRepository):
    """
    Handles database operations for Reports.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """
        Initializes the repository with the reports collection name.
        """
        super().__init__(db, "reports")

    async def create_report(self, report: Report) -> Report:
        """
        Insert a new content report.
        """
        report_data = report.model_dump(by_alias=True, exclude={"id"})
        if report.id:
            report_data["_id"] = ObjectId(report.id)
            
        created = await self.create(report_data)
        return Report.model_validate(created)

    async def get_report(self, report_id: str) -> Report:
        """
        Retrieve a single report by ID.
        """
        doc = await self.find_by_id(report_id)
        return Report.model_validate(doc)

    async def update_report_status(self, report_id: str, status: ReportStatus, reviewer_id: str) -> Report:
        """
        Atomically update the status, reviewer, and review date of a report.
        """
        if not ObjectId.is_valid(report_id):
            raise DocumentNotFoundException(f"Invalid report ID: {report_id}")
            
        current_time = datetime.now(timezone.utc)
        try:
            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(report_id)},
                {
                    "$set": {
                        "status": status.value,
                        "reviewedBy": reviewer_id,
                        "reviewedAt": current_time
                    }
                },
                return_document=True
            )
            if not result:
                raise DocumentNotFoundException(f"Report {report_id} not found.")
            return Report.model_validate(result)
        except DocumentNotFoundException:
            raise
        except Exception as e:
            logger.error("Error updating report %s: %s", report_id, e)
            raise RepositoryException(message=f"Database update error: {e}")

    async def find_reports(
        self,
        status: Optional[str] = None,
        reason: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> Tuple[List[Report], Optional[str]]:
        """
        Retrieve reports, filtered optionally by status or reason, sorted by createdAt descending.
        """
        filters: Dict[str, Any] = {}
        if status:
            filters["status"] = status
        if reason:
            filters["reason"] = reason
            
        sort = [("createdAt", -1), ("_id", -1)]
        
        docs, next_cursor = await self.find_many(filters, sort=sort, limit=limit, cursor=cursor)
        reports = [Report.model_validate(doc) for doc in docs]
        return reports, next_cursor

    async def has_user_reported(self, post_id: str, user_id: str) -> bool:
        """
        Check if a user has already reported a specific post.
        """
        return await self.exists({"postId": post_id, "reportedBy": user_id})

    async def count_reports(self, post_id: str) -> int:
        """
        Get total reports count for a specific post.
        """
        return await self.count({"postId": post_id})
