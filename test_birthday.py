import unittest
import sys
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append("/Users/akshaykumarmaldhure/work/matrimony-api")

from app.community.enums import PostType, PostStatus, Visibility
from app.community.models.post import (
    Post,
    Content,
    Moderation,
    AuthorSnapshot,
    VisibilitySettings,
    BirthdayMetadata,
)
from app.community.schemas.post import PostCreate, PostResponse
from app.community.services.birthday import BirthdayPostService


class MockAsyncCursor:
    def __init__(self, data):
        self.data = data
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.data):
            raise StopAsyncIteration
        val = self.data[self.index]
        self.index += 1
        return val


class TestBirthdayPosts(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.author = AuthorSnapshot(
            userId="user_123",
            profileId="profile_456",
            fullName="Jane Doe",
            profileImage=None,
            verified=True,
            paidMember=False,
        )
        self.content = Content(
            title="Happy Birthday!",
            body="Wishing you a great day!",
            images=[],
        )

    def test_birthday_enum_exists(self):
        self.assertEqual(PostType.BIRTHDAY, "BIRTHDAY")

    def test_birthday_metadata_validation(self):
        # Valid Birthday metadata
        bday = datetime.now(timezone.utc)
        meta = BirthdayMetadata(profileId="profile_456", birthdayDate=bday)
        self.assertEqual(meta.profileId, "profile_456")
        self.assertEqual(meta.birthdayDate, bday)

        # Missing fields in metadata should fail
        with self.assertRaises(ValidationError):
            BirthdayMetadata(profileId="profile_456")

    def test_expires_at_calculation(self):
        # Test birthday date: 2026-08-08 12:00:00 (UTC or timezone naive)
        bdate = datetime(2026, 8, 8, 12, 0, 0)
        
        post = Post(
            type=PostType.BIRTHDAY,
            author=self.author,
            content=self.content,
            metadata=BirthdayMetadata(profileId="profile_456", birthdayDate=bdate),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        
        # Expected expiresAt: 2026-08-09 00:00:00 IST -> 2026-08-08 18:30:00 UTC
        expected_expiry = datetime(2026, 8, 8, 18, 30, 0, tzinfo=timezone.utc)
        self.assertIsNotNone(post.expiresAt)
        self.assertEqual(post.expiresAt.astimezone(timezone.utc), expected_expiry)

    def test_post_response_serialization(self):
        bdate = datetime(2026, 8, 8, 0, 0, 0)
        post = Post(
            type=PostType.BIRTHDAY,
            author=self.author,
            content=self.content,
            metadata=BirthdayMetadata(profileId="profile_456", birthdayDate=bdate),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        
        post_dict = post.model_dump(by_alias=True)
        response = PostResponse.model_validate(post_dict)
        self.assertEqual(response.type, PostType.BIRTHDAY)
        self.assertEqual(response.metadata.profileId, "profile_456")
        self.assertIsNotNone(response.expiresAt)

    def test_reject_birthday_from_post_create(self):
        # Clients attempting to create BIRTHDAY post should be rejected
        with self.assertRaises(ValidationError) as ctx:
            PostCreate(
                type=PostType.BIRTHDAY,
                content=self.content,
                metadata=BirthdayMetadata(profileId="profile_456", birthdayDate=datetime.now(timezone.utc)),
                visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            )
        self.assertIn("Birthday posts cannot be created by clients directly.", str(ctx.exception))

    def test_existing_post_types_remain_unaffected(self):
        # A normal POST creation via PostCreate should be successful and default to DRAFT/PENDING if provided
        pc = PostCreate(
            type=PostType.POST,
            content=self.content,
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        self.assertEqual(pc.type, PostType.POST)
        
        # A normal POST model instance should not have expiresAt calculated
        post = Post(
            type=PostType.POST,
            author=self.author,
            content=self.content,
            moderation=Moderation(status=PostStatus.PENDING_REVIEW),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        self.assertIsNone(post.expiresAt)

    @patch("database.db_manager.get_collection")
    async def test_generate_birthday_posts(self, mock_get_collection):
        # Today's date in IST
        ist = timezone(timedelta(hours=5, minutes=30))
        today_ist = datetime.now(ist)

        # Build mock profiles
        mock_profiles = [
            # 1. Eligible Profile
            {
                "_id": "prof_eligible",
                "full_name": "Eligible User",
                "active": True,
                "is_verified": True,
                "birth_date": datetime(1995, today_ist.month, today_ist.day),
                "images": ["http://example.com/img1.jpg"]
            },
            # 2. Ineligible: Active but not verified
            {
                "_id": "prof_not_verified",
                "full_name": "Not Verified",
                "active": True,
                "is_verified": False,
                "birth_date": datetime(1995, today_ist.month, today_ist.day)
            },
            # 3. Ineligible: Verified but inactive
            {
                "_id": "prof_inactive",
                "full_name": "Inactive User",
                "active": False,
                "is_verified": True,
                "birth_date": datetime(1995, today_ist.month, today_ist.day)
            },
            # 4. Ineligible: Active and verified but different birthday
            {
                "_id": "prof_wrong_bday",
                "full_name": "Wrong Birthday",
                "active": True,
                "is_verified": True,
                "birth_date": datetime(1995, (today_ist.month % 12) + 1, today_ist.day)
            },
            # 5. Eligible with string birth_date
            {
                "_id": "prof_str_eligible",
                "full_name": "Str Eligible User",
                "active": True,
                "is_verified": True,
                "birth_date": f"1990-{today_ist.month:02d}-{today_ist.day:02d}T00:00:00.000Z"
            }
        ]

        # Setup mock collection and query cursor
        mock_collection = MagicMock()
        mock_collection.find.return_value = MockAsyncCursor(mock_profiles)
        mock_get_collection.return_value = mock_collection

        # Mock PostRepository
        mock_post_repo = MagicMock()
        mock_post_repo.collection = AsyncMock()
        mock_post_repo.collection.find_one.return_value = None  # None exist initially
        mock_post_repo.create_post = AsyncMock()

        service = BirthdayPostService(mock_post_repo)
        created_count = await service.generate_birthday_posts()

        # Check only two profiles were eligible
        self.assertEqual(created_count, 2)
        self.assertEqual(mock_post_repo.create_post.call_count, 2)

        # Verify the structure of created posts
        calls = mock_post_repo.create_post.call_args_list
        post_1 = calls[0][0][0]
        self.assertEqual(post_1.type, PostType.BIRTHDAY)
        self.assertEqual(post_1.moderation.status, PostStatus.APPROVED)
        self.assertEqual(post_1.author.userId, "system")
        self.assertEqual(post_1.metadata.profileId, "prof_eligible")
        self.assertEqual(post_1.content.images, ["http://example.com/img1.jpg"])
        
        # Test duplicate prevention (idempotency)
        # Reset mocks
        mock_post_repo.create_post.reset_mock()
        mock_collection.find.return_value = MockAsyncCursor(mock_profiles)
        
        # Let's say one post already exists in the database
        async def mock_find_one(filter_dict):
            if "prof_eligible" in filter_dict["_id"]:
                return {"_id": filter_dict["_id"]}
            return None

        mock_post_repo.collection.find_one.side_effect = mock_find_one
        
        created_count_2 = await service.generate_birthday_posts()
        # Only the string eligible post should be created since the first one was skipped
        self.assertEqual(created_count_2, 1)
        mock_post_repo.create_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
