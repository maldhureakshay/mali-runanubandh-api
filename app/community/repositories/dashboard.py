"""
Moderation Dashboard Repository module.

Provides database access layer and MongoDB aggregation pipelines 
for dashboard statistics and analytics.
"""

from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from app.community.enums import PostStatus, PostType
from app.events.event_types import EventType

logger = logging.getLogger(__name__)


class ModerationDashboardRepository:
    """
    Repository for executing high-performance aggregations across moderation collections.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self.posts_collection = db["posts"]
        self.reviews_collection = db["post_reviews"]

    async def aggregate_summary_stats(self) -> Dict[str, Any]:
        """
        Calculates summary counts for posts in various states.
        """
        now = datetime.now(timezone.utc)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = start_of_today - timedelta(days=start_of_today.weekday())
        start_of_month = start_of_today.replace(day=1)

        pipeline = [
            {
                "$facet": {
                    "statusCounts": [
                        {"$group": {"_id": "$moderation.status", "count": {"$sum": 1}}}
                    ],
                    "approvedToday": [
                        {"$match": {"moderation.status": PostStatus.APPROVED.value, "publishedAt": {"$gte": start_of_today}}},
                        {"$count": "count"}
                    ],
                    "approvedThisWeek": [
                        {"$match": {"moderation.status": PostStatus.APPROVED.value, "publishedAt": {"$gte": start_of_week}}},
                        {"$count": "count"}
                    ],
                    "approvedThisMonth": [
                        {"$match": {"moderation.status": PostStatus.APPROVED.value, "publishedAt": {"$gte": start_of_month}}},
                        {"$count": "count"}
                    ]
                }
            }
        ]

        cursor = self.posts_collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        
        if not result:
            return {}

        data = result[0]
        status_counts = {item["_id"]: item["count"] for item in data.get("statusCounts", [])}
        
        return {
            "pendingReviewCount": status_counts.get(PostStatus.PENDING_REVIEW.value, 0),
            "needsChangesCount": status_counts.get(PostStatus.NEEDS_CHANGES.value, 0),
            "draftCount": status_counts.get(PostStatus.DRAFT.value, 0),
            "archivedCount": status_counts.get(PostStatus.ARCHIVED.value, 0),
            "deletedCount": status_counts.get(PostStatus.DELETED.value, 0),
            "totalCommunityPosts": sum(count for status, count in status_counts.items() if status != PostStatus.DELETED.value),
            "approvedToday": data.get("approvedToday", [{"count": 0}])[0].get("count", 0) if data.get("approvedToday") else 0,
            "approvedThisWeek": data.get("approvedThisWeek", [{"count": 0}])[0].get("count", 0) if data.get("approvedThisWeek") else 0,
            "approvedThisMonth": data.get("approvedThisMonth", [{"count": 0}])[0].get("count", 0) if data.get("approvedThisMonth") else 0,
        }

    async def aggregate_moderation_metrics(self) -> Dict[str, Any]:
        """
        Calculates moderation metrics like approval rates and average review times.
        """
        # Reviews pipeline
        reviews_pipeline = [
            {
                "$group": {
                    "_id": None,
                    "totalReviews": {"$sum": 1},
                    "approvals": {
                        "$sum": {"$cond": [{"$eq": ["$action", EventType.POST_APPROVED.value]}, 1, 0]}
                    },
                    "needsChanges": {
                        "$sum": {"$cond": [{"$eq": ["$action", EventType.POST_NEEDS_CHANGES.value]}, 1, 0]}
                    }
                }
            }
        ]

        # Posts pipeline for pending times
        posts_pipeline = [
            {"$match": {"moderation.status": PostStatus.PENDING_REVIEW.value, "moderation.submittedAt": {"$ne": None}}},
            {
                "$group": {
                    "_id": None,
                    "totalPending": {"$sum": 1},
                    "oldestPending": {"$min": "$moderation.submittedAt"},
                    "newestPending": {"$max": "$moderation.submittedAt"}
                }
            }
        ]

        reviews_cursor = self.reviews_collection.aggregate(reviews_pipeline)
        posts_cursor = self.posts_collection.aggregate(posts_pipeline)
        
        reviews_result = await reviews_cursor.to_list(length=1)
        posts_result = await posts_cursor.to_list(length=1)

        data = {}
        if reviews_result:
            rr = reviews_result[0]
            total = rr.get("totalReviews", 0)
            data["totalReviews"] = total
            if total > 0:
                data["approvalRate"] = round((rr.get("approvals", 0) / total) * 100, 2)
                data["needsChangesRate"] = round((rr.get("needsChanges", 0) / total) * 100, 2)
            else:
                data["approvalRate"] = 0.0
                data["needsChangesRate"] = 0.0

        if posts_result:
            pr = posts_result[0]
            data["totalPending"] = pr.get("totalPending", 0)
            
            oldest = pr.get("oldestPending")
            data["oldestPendingPostDate"] = oldest.isoformat() if oldest else None
            
            newest = pr.get("newestPending")
            data["newestPendingPostDate"] = newest.isoformat() if newest else None

        # For average times, in a real highly complex system we'd use `$dateDiff` between events, 
        # but for now we mock the averages or leave them 0 to avoid highly expensive nested self-lookups
        data["averageReviewTimeMinutes"] = 0.0
        data["averageResubmissionTimeMinutes"] = 0.0

        return data

    async def aggregate_post_analytics(self) -> Dict[str, Any]:
        """
        Calculates posts analytics breakdown by Type and Status.
        """
        pipeline = [
            {
                "$facet": {
                    "byType": [
                        {"$group": {"_id": "$type", "count": {"$sum": 1}}}
                    ],
                    "byStatus": [
                        {"$group": {"_id": "$moderation.status", "count": {"$sum": 1}}}
                    ]
                }
            }
        ]

        cursor = self.posts_collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if not result:
            return {"byType": {}, "byStatus": {}}

        data = result[0]
        by_type = {item["_id"]: item["count"] for item in data.get("byType", []) if item["_id"]}
        by_status = {item["_id"]: item["count"] for item in data.get("byStatus", []) if item["_id"]}

        return {"byType": by_type, "byStatus": by_status}

    async def aggregate_moderator_activity(self) -> List[Dict[str, Any]]:
        """
        Calculates activity statistics grouped by moderator.
        """
        now = datetime.now(timezone.utc)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = start_of_today - timedelta(days=start_of_today.weekday())

        pipeline = [
            # Only look at moderator actions
            {"$match": {"moderatorId": {"$ne": None}}},
            {
                "$group": {
                    "_id": "$moderatorId",
                    "totalReviews": {"$sum": 1},
                    "approvals": {
                        "$sum": {"$cond": [{"$eq": ["$action", EventType.POST_APPROVED.value]}, 1, 0]}
                    },
                    "needsChanges": {
                        "$sum": {"$cond": [{"$eq": ["$action", EventType.POST_NEEDS_CHANGES.value]}, 1, 0]}
                    },
                    "reviewsToday": {
                        "$sum": {"$cond": [{"$gte": ["$createdAt", start_of_today]}, 1, 0]}
                    },
                    "reviewsThisWeek": {
                        "$sum": {"$cond": [{"$gte": ["$createdAt", start_of_week]}, 1, 0]}
                    },
                    "lastReviewTime": {"$max": "$createdAt"}
                }
            },
            # Sort by total reviews descending
            {"$sort": {"totalReviews": -1}}
        ]

        cursor = self.reviews_collection.aggregate(pipeline)
        results = await cursor.to_list(length=100)
        
        # Convert _id to moderatorId string
        for item in results:
            item["moderatorId"] = str(item.pop("_id"))
            item["averageReviewTimeMinutes"] = 0.0 # Mocked for simplicity without complex window functions
            if item.get("lastReviewTime"):
                item["lastReviewTime"] = item["lastReviewTime"].isoformat()
                
        return results

    async def aggregate_trend_analytics(self, period: str) -> List[Dict[str, Any]]:
        """
        Calculates trend analytics over time.
        period: 'daily', 'weekly', 'monthly'
        """
        if period == "monthly":
            date_format = "%Y-%m"
        elif period == "weekly":
            date_format = "%Y-%U"
        else: # daily
            date_format = "%Y-%m-%d"

        pipeline = [
            {
                "$group": {
                    "_id": {"$dateToString": {"format": date_format, "date": "$createdAt"}},
                    "submittedPosts": {
                        "$sum": {"$cond": [{"$eq": ["$action", EventType.POST_SUBMITTED.value]}, 1, 0]}
                    },
                    "approvedPosts": {
                        "$sum": {"$cond": [{"$eq": ["$action", EventType.POST_APPROVED.value]}, 1, 0]}
                    },
                    "needsChanges": {
                        "$sum": {"$cond": [{"$eq": ["$action", EventType.POST_NEEDS_CHANGES.value]}, 1, 0]}
                    },
                    "resubmissions": {
                        "$sum": {"$cond": [{"$eq": ["$action", EventType.POST_RESUBMITTED.value]}, 1, 0]}
                    },
                    "archivedPosts": {
                        "$sum": {"$cond": [{"$eq": ["$action", EventType.POST_ARCHIVED.value]}, 1, 0]}
                    }
                }
            },
            {"$sort": {"_id": 1}},
            {"$limit": 90} # Limit to 90 periods
        ]

        cursor = self.reviews_collection.aggregate(pipeline)
        results = await cursor.to_list(length=90)
        
        for item in results:
            item["date"] = item.pop("_id")
            
        return results
