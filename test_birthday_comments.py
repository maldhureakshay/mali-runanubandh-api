import unittest
import sys
from datetime import datetime, timezone, timedelta
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
from app.community.models.comment import Comment
from app.community.services.comment import CommentService
from app.community.services.exceptions import ValidationException, PostDeletedException, PostNotFoundException


class TestBirthdayComments(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_comment_repo = MagicMock()
        self.mock_post_repo = MagicMock()
        self.comment_service = CommentService(
            comment_repo=self.mock_comment_repo,
            post_repo=self.mock_post_repo
        )

        self.author = AuthorSnapshot(
            userId="user_123",
            profileId="profile_456",
            fullName="Jane Doe",
            verified=True,
            paidMember=False,
        )
        self.system_author = AuthorSnapshot(
            userId="system",
            profileId="system",
            fullName="System",
            verified=True,
            paidMember=True
        )
        self.birthday_content = Content(
            title="Happy Birthday!",
            body="Wishing you a great day!",
            images=[]
        )
        self.birthday_metadata = BirthdayMetadata(
            profileId="profile_456",
            birthdayDate=datetime(2026, 8, 8, tzinfo=timezone.utc)
        )

    async def test_comment_on_active_approved_birthday_post(self):
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)
        
        post = Post(
            id="birthday_active",
            type=PostType.BIRTHDAY,
            author=self.system_author,
            content=self.birthday_content,
            metadata=self.birthday_metadata,
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
            publishedAt=now,
            expiresAt=tomorrow
        )

        self.mock_post_repo.get_post = AsyncMock(return_value=post)
        self.mock_post_repo.increment_comments = AsyncMock()
        
        created_comment = Comment(
            id="comment_123",
            postId="birthday_active",
            author=self.author,
            comment="Happy Birthday! 🎂",
            edited=False,
            createdAt=now,
            updatedAt=now
        )
        self.mock_comment_repo.create_comment = AsyncMock(return_value=created_comment)

        result = await self.comment_service.create_comment(
            post_id="birthday_active",
            author=self.author,
            comment_text="Happy Birthday! 🎂"
        )

        self.assertEqual(result.comment, "Happy Birthday! 🎂")
        self.mock_post_repo.increment_comments.assert_called_once_with("birthday_active")

    async def test_comment_on_expired_birthday_post_rejected(self):
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        two_days_ago = now - timedelta(days=2)
        
        expired_metadata = BirthdayMetadata(
            profileId="profile_456",
            birthdayDate=two_days_ago
        )
        
        post = Post(
            id="birthday_expired",
            type=PostType.BIRTHDAY,
            author=self.system_author,
            content=self.birthday_content,
            metadata=expired_metadata,
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=yesterday,
            updatedAt=now,
            publishedAt=yesterday
        )

        self.mock_post_repo.get_post = AsyncMock(return_value=post)

        with self.assertRaises(ValidationException) as ctx:
            await self.comment_service.create_comment(
                post_id="birthday_expired",
                author=self.author,
                comment_text="Belated Happy Birthday!"
            )
        self.assertIn("Cannot comment on an expired birthday post.", str(ctx.exception))

    async def test_comment_on_non_approved_birthday_post_rejected(self):
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)
        
        post = Post(
            id="birthday_pending",
            type=PostType.BIRTHDAY,
            author=self.system_author,
            content=self.birthday_content,
            metadata=self.birthday_metadata,
            moderation=Moderation(status=PostStatus.PENDING_REVIEW),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
            publishedAt=None,
            expiresAt=tomorrow
        )

        self.mock_post_repo.get_post = AsyncMock(return_value=post)

        with self.assertRaises(ValidationException) as ctx:
            await self.comment_service.create_comment(
                post_id="birthday_pending",
                author=self.author,
                comment_text="Happy Birthday!"
            )
        self.assertIn("Cannot comment on a non-approved birthday post.", str(ctx.exception))

    async def test_comment_on_normal_post_unaffected(self):
        now = datetime.now(timezone.utc)
        
        post = Post(
            id="normal_post",
            type=PostType.POST,
            author=self.author,
            content=Content(body="This is a normal post"),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
            publishedAt=now
        )

        self.mock_post_repo.get_post = AsyncMock(return_value=post)
        self.mock_post_repo.increment_comments = AsyncMock()
        
        created_comment = Comment(
            id="comment_normal",
            postId="normal_post",
            author=self.author,
            comment="Nice post!",
            edited=False,
            createdAt=now,
            updatedAt=now
        )
        self.mock_comment_repo.create_comment = AsyncMock(return_value=created_comment)

        result = await self.comment_service.create_comment(
            post_id="normal_post",
            author=self.author,
            comment_text="Nice post!"
        )

        self.assertEqual(result.comment, "Nice post!")
        self.mock_post_repo.increment_comments.assert_called_once_with("normal_post")


if __name__ == "__main__":
    unittest.main()
