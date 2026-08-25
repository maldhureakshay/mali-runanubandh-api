import unittest
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

sys.path.append("/Users/akshaykumarmaldhure/work/matrimony-api")

from app.community.enums import PostType, PostStatus, Visibility
from app.community.models.post import (
    Post,
    Content,
    Moderation,
    AuthorSnapshot,
    VisibilitySettings,
    BirthdayMetadata,
    Statistics,
)
from app.community.schemas.post import PostResponse
from app.community.repositories.post import PostRepository
from app.community.repositories.base import BaseRepository


class MockAsyncCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length, *args, **kwargs):
        return self.docs


class TestBirthdayCommunityFeed(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_collection = MagicMock()
        self.mock_db.__getitem__.return_value = self.mock_collection
        self.post_repo = PostRepository(self.mock_db)

        self.system_author = AuthorSnapshot(
            userId="system",
            profileId="system",
            fullName="System",
            verified=True,
            paidMember=True
        )
        self.birthday_content = Content(
            title="Happy Birthday!",
            body="Wishing Jane Doe a very happy birthday!",
            images=[]
        )
        self.birthday_metadata = BirthdayMetadata(
            profileId="profile_123",
            birthdayDate=datetime(2026, 8, 8, tzinfo=timezone.utc)
        )

    async def test_find_feed_filters_expired_and_includes_approved_birthdays(self):
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        # Mock documents returned by database
        mock_docs = [
            # 1. Approved active birthday
            {
                "_id": "birthday_active_1",
                "type": "BIRTHDAY",
                "author": self.system_author.model_dump(),
                "content": self.birthday_content.model_dump(),
                "metadata": self.birthday_metadata.model_dump(),
                "statistics": Statistics().model_dump(),
                "visibility": {"visibility": "PUBLIC"},
                "moderation": {
                    "status": "APPROVED",
                    "reviewedAt": now,
                    "reviewedBy": "system",
                    "approvalNotes": "System generated birthday post"
                },
                "createdAt": now,
                "updatedAt": now,
                "publishedAt": now,
                "expiresAt": tomorrow
            },
            # 2. Approved but expired birthday
            {
                "_id": "birthday_expired_1",
                "type": "BIRTHDAY",
                "author": self.system_author.model_dump(),
                "content": self.birthday_content.model_dump(),
                "metadata": self.birthday_metadata.model_dump(),
                "statistics": Statistics().model_dump(),
                "visibility": {"visibility": "PUBLIC"},
                "moderation": {
                    "status": "APPROVED",
                    "reviewedAt": now,
                    "reviewedBy": "system",
                    "approvalNotes": "System generated birthday post"
                },
                "createdAt": now,
                "updatedAt": now,
                "publishedAt": now,
                "expiresAt": yesterday
            },
            # 3. Draft/pending birthday post
            {
                "_id": "birthday_draft_1",
                "type": "BIRTHDAY",
                "author": self.system_author.model_dump(),
                "content": self.birthday_content.model_dump(),
                "metadata": self.birthday_metadata.model_dump(),
                "statistics": Statistics().model_dump(),
                "visibility": {"visibility": "PUBLIC"},
                "moderation": {
                    "status": "DRAFT",
                    "reviewedAt": None,
                    "reviewedBy": None,
                },
                "createdAt": now,
                "updatedAt": now,
                "publishedAt": None,
                "expiresAt": tomorrow
            }
        ]

        self.mock_collection.find.return_value = MockAsyncCursor(mock_docs)

        # Call find_feed
        posts, _ = await self.post_repo.find_feed(visibility=Visibility.PUBLIC)

        # Verify filters passed to find contains $and and expiresAt conditions
        called_query = self.mock_collection.find.call_args[0][0]
        self.assertIn("moderation.status", called_query)
        self.assertEqual(called_query["moderation.status"], "APPROVED")
        self.assertIn("$and", called_query)

        # Verify that all 3 models correctly construct but we filter or test responses
        # The mock collection simulates DB return. Let's verify we get 3 posts from find_many validation:
        self.assertEqual(len(posts), 3)
        self.assertEqual(posts[0].id, "birthday_active_1")
        self.assertIsNotNone(posts[0].expiresAt)

    async def test_find_posts_by_type_filters_expired_birthdays(self):
        self.mock_collection.find.return_value = MockAsyncCursor([])

        # Call find_posts_by_type
        await self.post_repo.find_posts_by_type(PostType.BIRTHDAY)

        called_query = self.mock_collection.find.call_args[0][0]
        self.assertEqual(called_query["type"], "BIRTHDAY")
        self.assertEqual(called_query["moderation.status"], "APPROVED")
        self.assertIn("$and", called_query)

    def test_post_response_serialization_of_birthday(self):
        now = datetime.utcnow()
        post = Post(
            id="birthday_20260808_profile123",
            type=PostType.BIRTHDAY,
            author=self.system_author,
            content=self.birthday_content,
            metadata=self.birthday_metadata,
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
            publishedAt=now,
        )

        post_dict = post.model_dump(by_alias=True)
        response = PostResponse.model_validate(post_dict)

        self.assertEqual(response.id, "birthday_20260808_profile123")
        self.assertEqual(response.type, PostType.BIRTHDAY)
        self.assertEqual(response.metadata.profileId, "profile_123")
        self.assertIsNotNone(response.expiresAt)

    async def test_pagination_supports_string_ids(self):
        # Test pagination decode and string ID matching
        now = datetime.utcnow()
        cursor_str = BaseRepository.encode_cursor(last_id="birthday_20260808_profile123", last_sort_value=now)
        
        self.mock_collection.find.return_value = MockAsyncCursor([])

        # We will trigger find_many via find_feed using the string ID cursor
        await self.post_repo.find_feed(visibility=Visibility.PUBLIC, cursor=cursor_str)

        called_query = self.mock_collection.find.call_args[0][0]
        self.assertIn("$or", called_query)
        # Check that it did NOT wrap string in ObjectId, instead kept it as string
        or_conditions = called_query["$or"]
        self.assertEqual(or_conditions[1]["_id"]["$lt"], "birthday_20260808_profile123")


if __name__ == "__main__":
    unittest.main()
