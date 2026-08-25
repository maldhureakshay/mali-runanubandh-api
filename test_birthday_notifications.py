import unittest
import sys
import datetime
from datetime import timezone, timedelta
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
from app.events.event_types import EventType
from app.events.base_event import BaseEvent
from app.events.handlers.notification_handler import NotificationHandler


class TestBirthdayNotifications(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_comment_repo = MagicMock()
        self.mock_post_repo = MagicMock()
        self.mock_event_publisher = AsyncMock()
        
        self.comment_service = CommentService(
            comment_repo=self.mock_comment_repo,
            post_repo=self.mock_post_repo,
            event_publisher=self.mock_event_publisher
        )

        self.mock_notification_service = AsyncMock()
        self.mock_db = MagicMock()
        self.mock_posts_col = AsyncMock()
        self.mock_profiles_col = AsyncMock()
        self.mock_db.posts = self.mock_posts_col
        self.mock_db.profiles = self.mock_profiles_col

        self.notification_handler = NotificationHandler(
            notification_service=self.mock_notification_service,
            db=self.mock_db
        )

        self.author = AuthorSnapshot(
            userId="commenter_123",
            profileId="profile_commenter",
            fullName="Jane Doe",
            verified=True,
            paidMember=False,
        )
        self.birthday_recipient_profile = {
            "_id": "profile_birthday_person",
            "userId": "birthday_person_123",
            "full_name": "Birthday Person"
        }
        self.commenter_profile = {
            "_id": "profile_commenter",
            "userId": "commenter_123",
            "full_name": "Jane Doe"
        }

        self.birthday_content = Content(
            title="Happy Birthday!",
            body="Wishing you a great day!",
            images=[]
        )
        self.birthday_metadata = BirthdayMetadata(
            profileId="profile_birthday_person",
            birthdayDate=datetime.datetime(2026, 8, 8, tzinfo=timezone.utc)
        )

    async def test_create_comment_publishes_birthday_wish_created(self):
        now = datetime.datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)
        
        post = Post(
            id="birthday_post_123",
            type=PostType.BIRTHDAY,
            author=AuthorSnapshot(userId="system", profileId="system", fullName="System"),
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
            id="comment_wish_123",
            postId="birthday_post_123",
            author=self.author,
            comment="Happy Birthday! 🎂",
            edited=False,
            createdAt=now,
            updatedAt=now
        )
        self.mock_comment_repo.create_comment = AsyncMock(return_value=created_comment)

        await self.comment_service.create_comment(
            post_id="birthday_post_123",
            author=self.author,
            comment_text="Happy Birthday! 🎂"
        )

        self.mock_event_publisher.publish.assert_called_once()
        called_args = self.mock_event_publisher.publish.call_args
        self.assertEqual(called_args[0][0], EventType.BIRTHDAY_WISH_CREATED)
        self.assertEqual(called_args[0][1]["postId"], "birthday_post_123")
        self.assertEqual(called_args[0][1]["birthdayProfileId"], "profile_birthday_person")
        self.assertEqual(called_args[0][1]["commenterUserId"], "commenter_123")
        self.assertEqual(called_args[0][1]["commentId"], "comment_wish_123")

    async def test_notification_sent_on_birthday_wish_created_event(self):
        now = datetime.datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)

        post_doc = {
            "_id": "birthday_post_123",
            "type": "BIRTHDAY",
            "moderation": {"status": "APPROVED"},
            "expiresAt": tomorrow
        }
        
        self.mock_posts_col.find_one.return_value = post_doc
        
        # Async iterator mock for profiles
        async def mock_find_one_profile(query):
            if query.get("_id") == "profile_birthday_person":
                return self.birthday_recipient_profile
            if query.get("userId") == "commenter_123":
                return self.commenter_profile
            return None
        self.mock_profiles_col.find_one.side_effect = mock_find_one_profile

        event = BaseEvent(
            eventType=EventType.BIRTHDAY_WISH_CREATED,
            payload={
                "postId": "birthday_post_123",
                "birthdayProfileId": "profile_birthday_person",
                "commenterUserId": "commenter_123",
                "commentId": "comment_wish_123"
            }
        )

        await self.notification_handler.handle(event)

        self.mock_notification_service.create_notification.assert_called_once_with(
            recipient_user_id="birthday_person_123",
            actor_user_id="commenter_123",
            notification_type="BIRTHDAY_WISH",
            title="Happy Birthday!",
            message="Jane Doe wished you a Happy Birthday! 🎂",
            reference_type="COMMENT",
            reference_id="comment_wish_123"
        )

    async def test_self_comment_does_not_notify(self):
        now = datetime.datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)

        post_doc = {
            "_id": "birthday_post_123",
            "type": "BIRTHDAY",
            "moderation": {"status": "APPROVED"},
            "expiresAt": tomorrow
        }
        self.mock_posts_col.find_one.return_value = post_doc
        self.mock_profiles_col.find_one.return_value = self.birthday_recipient_profile

        # Payload shows commenter is same as birthday person
        event = BaseEvent(
            eventType=EventType.BIRTHDAY_WISH_CREATED,
            payload={
                "postId": "birthday_post_123",
                "birthdayProfileId": "profile_birthday_person",
                "commenterUserId": "birthday_person_123",
                "commentId": "comment_wish_123"
            }
        )

        await self.notification_handler.handle(event)
        self.mock_notification_service.create_notification.assert_not_called()

    async def test_expired_post_does_not_notify(self):
        now = datetime.datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        post_doc = {
            "_id": "birthday_post_123",
            "type": "BIRTHDAY",
            "moderation": {"status": "APPROVED"},
            "expiresAt": yesterday
        }
        self.mock_posts_col.find_one.return_value = post_doc

        event = BaseEvent(
            eventType=EventType.BIRTHDAY_WISH_CREATED,
            payload={
                "postId": "birthday_post_123",
                "birthdayProfileId": "profile_birthday_person",
                "commenterUserId": "commenter_123",
                "commentId": "comment_wish_123"
            }
        )

        await self.notification_handler.handle(event)
        self.mock_notification_service.create_notification.assert_not_called()


if __name__ == "__main__":
    unittest.main()
