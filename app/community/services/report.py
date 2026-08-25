"""
Report Service module.

Implements business logic for managing abuse and spam Reports on community posts.
"""

from datetime import datetime, timezone
import logging
from typing import Any, List, Optional, Tuple

from pymongo.errors import DuplicateKeyError

from app.community.models.report import Report
from app.community.enums import PostStatus, ReportReason, ReportStatus
from app.community.repositories.post import PostRepository
from app.community.repositories.report import ReportRepository
from app.community.repositories.exceptions import DocumentNotFoundException
from app.community.services.exceptions import (
    DuplicateReportException,
    PostDeletedException,
    PostNotFoundException,
    ValidationException,
    CommentNotFoundException, # Placeholder if needed
)

from app.events.event_types import EventType

logger = logging.getLogger(__name__)


class ReportService:
    """
    Orchestrates business operations for reporting posts and counting reports.
    """

    def __init__(self, report_repo: ReportRepository, post_repo: PostRepository, event_publisher: Any = None) -> None:
        """
        Dependency injects ReportRepository, PostRepository and optional EventPublisher.
        """
        self.report_repo = report_repo
        self.post_repo = post_repo
        self.event_publisher = event_publisher

    async def report_post(
        self,
        post_id: str,
        reported_by: str,
        reason: ReportReason,
        description: Optional[str] = None,
        session: Any = None
    ) -> Report:
        """
        File a report against a post, ensuring only one report per user/post, and incrementing reportsCount.
        """
        # 1. Verify post exists and is not deleted
        try:
            post = await self.post_repo.get_post(post_id)
            if post.moderation.status == PostStatus.DELETED:
                raise PostDeletedException("Cannot report a deleted post.")
        except DocumentNotFoundException:
            raise PostNotFoundException("Cannot report a post that does not exist.")

        # 2. Prevent reporting own post
        if post.author.userId == reported_by:
            raise ValidationException("You cannot report your own post.")

        # 3. Prevent duplicate reports from the same user
        already_reported = await self.report_repo.has_user_reported(post_id, reported_by)
        if already_reported:
            logger.warning("Duplicate report attempt: User %s on post %s.", reported_by, post_id)
            raise DuplicateReportException()

        # 4. Create report document
        report_record = Report(
            postId=post_id,
            reportedBy=reported_by,
            reason=reason,
            description=description,
            status=ReportStatus.PENDING,
            createdAt=datetime.now(timezone.utc)
        )
        
        try:
            created = await self.report_repo.create_report(report_record)
        except DuplicateKeyError:
            logger.warning("Duplicate report attempt (DB constraint): User %s on post %s.", reported_by, post_id)
            raise DuplicateReportException()

        # 5. Increment reports count atomically
        await self.post_repo.increment_reports(post_id)
        
        logger.info("Report created: Filed against post %s by user %s. Reason: %s", post_id, reported_by, reason)
        if self.event_publisher:
            await self.event_publisher.publish(
                EventType.POST_REPORTED,
                created.model_dump(by_alias=True)
            )
        return created

    async def get_reports(
        self,
        status: Optional[str] = None,
        reason: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> Tuple[List[Report], Optional[str]]:
        """
        Retrieve reports with optional filters (status, reason) and cursor pagination.
        """
        return await self.report_repo.find_reports(status=status, reason=reason, limit=limit, cursor=cursor)

    async def get_report_details(self, report_id: str) -> Report:
        """
        Retrieve details of a specific report.
        """
        try:
            return await self.report_repo.get_report(report_id)
        except DocumentNotFoundException:
            raise ValidationException(f"Report with ID {report_id} does not exist.")

    async def dismiss_report(self, report_id: str, reviewer_id: str) -> Report:
        """
        Dismiss a report, marking it as DISMISSED and decrementing the post's report count.
        """
        try:
            report = await self.report_repo.get_report(report_id)
        except DocumentNotFoundException:
            raise ValidationException(f"Report with ID {report_id} does not exist.")

        if report.status == ReportStatus.DISMISSED:
            return report

        # Update report status to DISMISSED
        updated_report = await self.report_repo.update_report_status(report_id, ReportStatus.DISMISSED, reviewer_id)

        # Decrement reportsCount on the post
        try:
            await self.post_repo.decrement_reports(report.postId)
        except Exception as e:
            logger.warning("Failed to decrement report count for post %s: %s", report.postId, e)

        logger.info("Report dismissed: ID %s by reviewer %s.", report_id, reviewer_id)
        return updated_report

    async def review_report(self, report_id: str, reviewer_id: str) -> Report:
        """
        Mark a report as REVIEWED.
        """
        try:
            report = await self.report_repo.get_report(report_id)
        except DocumentNotFoundException:
            raise ValidationException(f"Report with ID {report_id} does not exist.")

        if report.status == ReportStatus.REVIEWED:
            return report

        updated_report = await self.report_repo.update_report_status(report_id, ReportStatus.REVIEWED, reviewer_id)
        logger.info("Report reviewed: ID %s marked as reviewed by %s.", report_id, reviewer_id)
        return updated_report
