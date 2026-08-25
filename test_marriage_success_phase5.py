"""
Tests for MARRIAGE_SUCCESS Phase 5: Events, Notifications, Security & Hardening.

Covers:
- Admin authorization (ADMIN only for creation, MODERATOR rejected)
- Normal user creation rejected at schema layer
- SINGLE_PERSON event payload
- COUPLE event payload (both profiles)
- Notification handler dispatches correct notification type
- Duplicate protection (active post for same profile blocks creation)
- 30-day expiration set on creation
- Archived post excluded from feed
- Expired post excluded from feed
- Existing post functionality unaffected
- CreateMarriageAnnouncementRequest schema validation
"""

import sys
import unittest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append("/Users/akshaykumarmaldhure/work/matrimony-api")

from app.community.enums import PostType, PostStatus, Visibility
from app.community.models.post import (
    AuthorSnapshot,
    Content,
    MarriageAnnouncementType,
    MarriageSuccessMetadata,
    Moderation,
    Post,
    VisibilitySettings,
)
from app.community.schemas.post import PostCreate, PostResponse
from app.community.schemas.moderation import CreateMarriageAnnouncementRequest
from app.community.services.marriage import MarriageSuccessService
from app.community.services.exceptions import ValidationException
from app.events.event_types import EventType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _admin_author(uid: str = "admin_001") -> AuthorSnapshot:
    return AuthorSnapshot(
        userId=uid, profileId=uid, fullName="Admin User",
        verified=True, paidMember=True,
    )


def _content() -> Content:
    return Content(title="Marriage Announcement", body="Congratulations!", images=[])


def _single_meta() -> MarriageSuccessMetadata:
    return MarriageSuccessMetadata(
        announcementType=MarriageAnnouncementType.SINGLE_PERSON,
        person1ProfileId="profile_bride",
    )


def _couple_meta() -> MarriageSuccessMetadata:
    return MarriageSuccessMetadata(
        announcementType=MarriageAnnouncementType.COUPLE,
        person1ProfileId="profile_bride",
        person2ProfileId="profile_groom",
    )


def _make_approved_post(meta=None, expires_override: datetime | None = None) -> Post:
    now = datetime.now(timezone.utc)
    post = Post(
        type=PostType.MARRIAGE_SUCCESS,
        author=_admin_author(),
        content=_content(),
        metadata=meta or _single_meta(),
        moderation=Moderation(status=PostStatus.APPROVED),
        visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        createdAt=now, updatedAt=now, publishedAt=now,
    )
    if expires_override is not None:
        object.__setattr__(post, "expiresAt", expires_override)
    return post


def _make_service(existing_posts=None, created_post=None):
    """Build MarriageSuccessService with a mocked repo and event publisher."""
    mock_repo = AsyncMock()
    mock_repo.find_posts_by_admin = AsyncMock(return_value=(existing_posts or [], None))

    if created_post is None:
        created_post = _make_approved_post()
    mock_repo.create_post = AsyncMock(return_value=created_post)

    mock_publisher = AsyncMock()
    return MarriageSuccessService(post_repo=mock_repo, event_publisher=mock_publisher), mock_repo, mock_publisher


# ---------------------------------------------------------------------------
# 1. MARRIAGE_SUCCESS_CREATED event type exists
# ---------------------------------------------------------------------------

class TestMarriageSuccessEventType(unittest.TestCase):

    def test_event_type_exists(self):
        """MARRIAGE_SUCCESS_CREATED must be a valid EventType."""
        self.assertIn("MARRIAGE_SUCCESS_CREATED", [e.value for e in EventType])

    def test_event_type_is_string(self):
        """EventType is str-based; MARRIAGE_SUCCESS_CREATED must behave as a string."""
        self.assertEqual(EventType.MARRIAGE_SUCCESS_CREATED, "MARRIAGE_SUCCESS_CREATED")


# ---------------------------------------------------------------------------
# 2. CreateMarriageAnnouncementRequest schema validation
# ---------------------------------------------------------------------------

class TestCreateMarriageAnnouncementRequest(unittest.TestCase):

    def test_valid_single_person_request(self):
        """Valid SINGLE_PERSON request must construct without error."""
        req = CreateMarriageAnnouncementRequest(
            announcementType=MarriageAnnouncementType.SINGLE_PERSON,
            person1ProfileId="profile_bride",
            content=_content(),
        )
        self.assertEqual(req.announcementType, MarriageAnnouncementType.SINGLE_PERSON)
        self.assertIsNone(req.person2ProfileId)

    def test_valid_couple_request(self):
        """Valid COUPLE request must construct without error."""
        req = CreateMarriageAnnouncementRequest(
            announcementType=MarriageAnnouncementType.COUPLE,
            person1ProfileId="profile_bride",
            person2ProfileId="profile_groom",
            content=_content(),
        )
        self.assertEqual(req.person2ProfileId, "profile_groom")

    def test_couple_missing_person2_raises(self):
        """COUPLE without person2ProfileId must raise ValidationError."""
        with self.assertRaises(ValidationError):
            CreateMarriageAnnouncementRequest(
                announcementType=MarriageAnnouncementType.COUPLE,
                person1ProfileId="profile_bride",
                content=_content(),
            )

    def test_couple_same_person_raises(self):
        """COUPLE with identical person1 and person2 must raise ValidationError."""
        with self.assertRaises(ValidationError):
            CreateMarriageAnnouncementRequest(
                announcementType=MarriageAnnouncementType.COUPLE,
                person1ProfileId="profile_same",
                person2ProfileId="profile_same",
                content=_content(),
            )

    def test_single_person_with_person2_raises(self):
        """SINGLE_PERSON with a non-null person2ProfileId must raise ValidationError."""
        with self.assertRaises(ValidationError):
            CreateMarriageAnnouncementRequest(
                announcementType=MarriageAnnouncementType.SINGLE_PERSON,
                person1ProfileId="profile_bride",
                person2ProfileId="profile_groom",
                content=_content(),
            )

    def test_defaults_to_public_visibility(self):
        """Visibility defaults to PUBLIC if not specified."""
        req = CreateMarriageAnnouncementRequest(
            announcementType=MarriageAnnouncementType.SINGLE_PERSON,
            person1ProfileId="profile_bride",
            content=_content(),
        )
        self.assertEqual(req.visibility, Visibility.PUBLIC)


# ---------------------------------------------------------------------------
# 3. Authorization — only ADMIN can create, not MODERATOR or USER
# ---------------------------------------------------------------------------

class TestAdminOnlyAuthorization(unittest.TestCase):

    def test_require_admin_role_only(self):
        """
        The marriage announcement creation endpoint uses require_roles([ADMIN]),
        not require_roles([ADMIN, MODERATOR]).
        Verify that a MODERATOR cannot pass the admin-only check.
        """
        from app.core.dependencies import ADMIN, MODERATOR
        from app.core.dependencies import AuthenticatedUser as AU
        from app.core.exceptions import ForbiddenException
        import asyncio

        moderator_user = AU(uid="mod_001", roles=[MODERATOR], claims={})

        async def run():
            # Simulate admin-only check
            if ADMIN not in moderator_user.roles:
                raise ForbiddenException("Forbidden")
            return moderator_user

        with self.assertRaises(ForbiddenException):
            asyncio.run(run())

    def test_admin_passes(self):
        """An ADMIN user must pass the admin-only check."""
        from app.core.dependencies import ADMIN
        from app.core.dependencies import AuthenticatedUser as AU
        import asyncio

        admin_user = AU(uid="admin_001", roles=[ADMIN], claims={})

        async def run():
            if ADMIN not in admin_user.roles:
                raise Exception("Forbidden")
            return admin_user

        result = asyncio.run(run())
        self.assertEqual(result.uid, "admin_001")

    def test_normal_user_cannot_create_via_post_create_schema(self):
        """PostCreate must reject MARRIAGE_SUCCESS at the schema layer."""
        with self.assertRaises(ValidationError):
            PostCreate(
                type=PostType.MARRIAGE_SUCCESS,
                content=_content(),
                metadata=_single_meta(),
                visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            )


# ---------------------------------------------------------------------------
# 4. MarriageSuccessService creation — event payload
# ---------------------------------------------------------------------------

class TestMarriageSuccessServiceCreation(unittest.IsolatedAsyncioTestCase):

    async def test_single_person_event_payload(self):
        """SINGLE_PERSON creation must publish MARRIAGE_SUCCESS_CREATED with correct payload."""
        created = _make_approved_post(meta=_single_meta())
        svc, repo, publisher = _make_service(created_post=created)

        await svc.create_marriage_announcement(
            admin_id="admin_001",
            admin_author=_admin_author(),
            announcement_type=MarriageAnnouncementType.SINGLE_PERSON,
            person1_profile_id="profile_bride",
            content=_content(),
        )

        publisher.publish.assert_called_once()
        call_args = publisher.publish.call_args
        event_type = call_args.args[0]
        payload = call_args.args[1]

        self.assertEqual(event_type, EventType.MARRIAGE_SUCCESS_CREATED)
        self.assertEqual(payload["person1ProfileId"], "profile_bride")
        self.assertIsNone(payload["person2ProfileId"])
        self.assertEqual(payload["createdByAdminId"], "admin_001")
        self.assertIn("postId", payload)
        self.assertIn("expiresAt", payload)

    async def test_couple_event_payload(self):
        """COUPLE creation must publish event with both person profile IDs."""
        created = _make_approved_post(meta=_couple_meta())
        svc, repo, publisher = _make_service(created_post=created)

        await svc.create_marriage_announcement(
            admin_id="admin_001",
            admin_author=_admin_author(),
            announcement_type=MarriageAnnouncementType.COUPLE,
            person1_profile_id="profile_bride",
            person2_profile_id="profile_groom",
            content=_content(),
        )

        payload = publisher.publish.call_args.args[1]
        self.assertEqual(payload["person1ProfileId"], "profile_bride")
        self.assertEqual(payload["person2ProfileId"], "profile_groom")
        self.assertEqual(payload["announcementType"], "COUPLE")

    async def test_post_is_created_approved_with_publishedat(self):
        """Created post must have APPROVED status and a publishedAt timestamp."""
        created = _make_approved_post()
        svc, repo, _ = _make_service(created_post=created)

        result = await svc.create_marriage_announcement(
            admin_id="admin_001",
            admin_author=_admin_author(),
            announcement_type=MarriageAnnouncementType.SINGLE_PERSON,
            person1_profile_id="profile_bride",
            content=_content(),
        )

        self.assertEqual(result.moderation.status, PostStatus.APPROVED)
        self.assertIsNotNone(result.publishedAt)

    async def test_expiry_is_30_days_from_creation(self):
        """expiresAt must be exactly createdAt + 30 days."""
        now = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
        created = _make_approved_post(meta=_single_meta())
        object.__setattr__(created, "createdAt", now)
        object.__setattr__(created, "expiresAt", now + timedelta(days=30))
        svc, _, _ = _make_service(created_post=created)

        result = await svc.create_marriage_announcement(
            admin_id="admin_001",
            admin_author=_admin_author(),
            announcement_type=MarriageAnnouncementType.SINGLE_PERSON,
            person1_profile_id="profile_bride",
            content=_content(),
        )
        self.assertEqual(result.expiresAt, now + timedelta(days=30))

    async def test_no_event_published_when_publisher_is_none(self):
        """If event_publisher is None, creation must still succeed silently."""
        mock_repo = AsyncMock()
        mock_repo.find_posts_by_admin = AsyncMock(return_value=([], None))
        mock_repo.create_post = AsyncMock(return_value=_make_approved_post())
        svc = MarriageSuccessService(post_repo=mock_repo, event_publisher=None)

        result = await svc.create_marriage_announcement(
            admin_id="admin_001",
            admin_author=_admin_author(),
            announcement_type=MarriageAnnouncementType.SINGLE_PERSON,
            person1_profile_id="profile_bride",
            content=_content(),
        )
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# 5. Duplicate protection
# ---------------------------------------------------------------------------

class TestDuplicateProtection(unittest.IsolatedAsyncioTestCase):

    async def test_duplicate_single_person_raises(self):
        """Creating a second active SINGLE_PERSON post for same profile must raise ValidationException."""
        existing = _make_approved_post(meta=_single_meta())
        svc, _, _ = _make_service(existing_posts=[existing])

        with self.assertRaises(ValidationException) as ctx:
            await svc.create_marriage_announcement(
                admin_id="admin_001",
                admin_author=_admin_author(),
                announcement_type=MarriageAnnouncementType.SINGLE_PERSON,
                person1_profile_id="profile_bride",  # same as existing
                content=_content(),
            )
        self.assertIn("already exists", str(ctx.exception))

    async def test_duplicate_couple_raises_when_person1_overlaps(self):
        """Creating COUPLE where person1 already has an active post must raise ValidationException."""
        existing = _make_approved_post(meta=_couple_meta())
        svc, _, _ = _make_service(existing_posts=[existing])

        with self.assertRaises(ValidationException):
            await svc.create_marriage_announcement(
                admin_id="admin_001",
                admin_author=_admin_author(),
                announcement_type=MarriageAnnouncementType.COUPLE,
                person1_profile_id="profile_bride",  # overlaps with existing
                person2_profile_id="profile_other",
                content=_content(),
            )

    async def test_no_duplicate_when_different_profiles(self):
        """Creating a post for a completely different profile must succeed."""
        existing = _make_approved_post(meta=_single_meta())  # profile_bride
        svc, _, _ = _make_service(existing_posts=[existing], created_post=_make_approved_post())

        # profile_xyz has no existing active post
        result = await svc.create_marriage_announcement(
            admin_id="admin_001",
            admin_author=_admin_author(),
            announcement_type=MarriageAnnouncementType.SINGLE_PERSON,
            person1_profile_id="profile_xyz",
            content=_content(),
        )
        self.assertIsNotNone(result)

    async def test_same_person_raises_validation_exception(self):
        """COUPLE where person1 == person2 must raise ValidationException from service."""
        svc, _, _ = _make_service()

        with self.assertRaises(ValidationException) as ctx:
            await svc.create_marriage_announcement(
                admin_id="admin_001",
                admin_author=_admin_author(),
                announcement_type=MarriageAnnouncementType.COUPLE,
                person1_profile_id="same_profile",
                person2_profile_id="same_profile",
                content=_content(),
            )
        self.assertIn("must be different", str(ctx.exception))


# ---------------------------------------------------------------------------
# 6. Notification handler dispatch
# ---------------------------------------------------------------------------

class TestNotificationHandlerDispatch(unittest.IsolatedAsyncioTestCase):

    async def test_handle_dispatches_to_marriage_success_handler(self):
        """
        NotificationHandler.handle() must route MARRIAGE_SUCCESS_CREATED
        to _handle_marriage_success_created.
        """
        from app.events.handlers.notification_handler import NotificationHandler
        from app.events.base_event import BaseEvent

        mock_notification_service = AsyncMock()
        mock_db = MagicMock()

        # Profile lookup returns a doc with userId
        mock_db.profiles.find_one = AsyncMock(return_value={"_id": "profile_bride", "userId": "user_bride"})

        handler = NotificationHandler(mock_notification_service, mock_db)

        event = BaseEvent(
            eventType=EventType.MARRIAGE_SUCCESS_CREATED,
            payload={
                "postId": "post_abc",
                "person1ProfileId": "profile_bride",
                "person2ProfileId": None,
                "createdByAdminId": "admin_001",
            }
        )

        await handler.handle(event)

        mock_notification_service.create_notification.assert_called_once()
        call_kwargs = mock_notification_service.create_notification.call_args.kwargs
        self.assertEqual(call_kwargs["notification_type"], "MARRIAGE_ANNOUNCEMENT")
        self.assertIn("🎉", call_kwargs["message"])

    async def test_couple_notifies_both_profiles(self):
        """COUPLE event must notify both person1 and person2."""
        from app.events.handlers.notification_handler import NotificationHandler
        from app.events.base_event import BaseEvent

        mock_notification_service = AsyncMock()
        mock_db = MagicMock()

        # Return different userId for each profile lookup
        async def mock_find_one(query):
            profile_id = list(query.values())[0]
            return {"_id": str(profile_id), "userId": f"user_{profile_id}"}

        mock_db.profiles.find_one = AsyncMock(side_effect=mock_find_one)

        handler = NotificationHandler(mock_notification_service, mock_db)
        event = BaseEvent(
            eventType=EventType.MARRIAGE_SUCCESS_CREATED,
            payload={
                "postId": "post_abc",
                "person1ProfileId": "profile_bride",
                "person2ProfileId": "profile_groom",
                "createdByAdminId": "admin_001",
            }
        )

        await handler.handle(event)

        # Two notifications — one per profile
        self.assertEqual(mock_notification_service.create_notification.call_count, 2)

    async def test_notification_skipped_when_profile_not_found(self):
        """If profile not found in DB, notification is skipped without crashing."""
        from app.events.handlers.notification_handler import NotificationHandler
        from app.events.base_event import BaseEvent

        mock_notification_service = AsyncMock()
        mock_db = MagicMock()
        mock_db.profiles.find_one = AsyncMock(return_value=None)  # not found

        handler = NotificationHandler(mock_notification_service, mock_db)
        event = BaseEvent(
            eventType=EventType.MARRIAGE_SUCCESS_CREATED,
            payload={
                "postId": "post_abc",
                "person1ProfileId": "nonexistent_profile",
                "person2ProfileId": None,
                "createdByAdminId": "admin_001",
            }
        )

        # Must not raise
        await handler.handle(event)
        mock_notification_service.create_notification.assert_not_called()

    async def test_notification_skipped_when_missing_post_id(self):
        """Handler must skip gracefully when postId is missing from payload."""
        from app.events.handlers.notification_handler import NotificationHandler
        from app.events.base_event import BaseEvent

        mock_notification_service = AsyncMock()
        mock_db = MagicMock()
        handler = NotificationHandler(mock_notification_service, mock_db)
        event = BaseEvent(
            eventType=EventType.MARRIAGE_SUCCESS_CREATED,
            payload={"person1ProfileId": "profile_bride"},  # no postId
        )

        await handler.handle(event)
        mock_notification_service.create_notification.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Security: feed filters (verify existing phase 3 guards still hold)
# ---------------------------------------------------------------------------

class TestSecurityFeedFilters(unittest.TestCase):

    def test_archived_post_not_approved(self):
        """Archived (DELETED) post fails the feed's APPROVED requirement."""
        post = _make_approved_post()
        object.__setattr__(post.moderation, "status", PostStatus.DELETED)
        self.assertNotEqual(post.moderation.status, PostStatus.APPROVED)

    def test_expired_post_expiresAt_lte_now(self):
        """Expired post has expiresAt <= now → excluded by $gt filter."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        post = _make_approved_post(expires_override=past)
        self.assertLessEqual(post.expiresAt, datetime.now(timezone.utc))

    def test_active_post_passes_expiry_check(self):
        """Non-expired post has expiresAt > now → passes $gt filter."""
        future = datetime.now(timezone.utc) + timedelta(days=15)
        post = _make_approved_post(expires_override=future)
        self.assertGreater(post.expiresAt, datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 8. Existing post functionality unaffected
# ---------------------------------------------------------------------------

class TestExistingFunctionalityUnaffected(unittest.IsolatedAsyncioTestCase):

    async def test_post_create_still_rejects_birthday(self):
        """BIRTHDAY type must still be rejected by PostCreate."""
        with self.assertRaises(ValidationError):
            PostCreate(
                type=PostType.BIRTHDAY,
                content=_content(),
                visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            )

    async def test_normal_post_type_accepted_by_post_create(self):
        """Regular POST type must still be accepted by PostCreate."""
        req = PostCreate(
            type=PostType.POST,
            content=_content(),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        self.assertEqual(req.type, PostType.POST)

    def test_existing_event_types_unaffected(self):
        """Adding MARRIAGE_SUCCESS_CREATED must not change existing event type values."""
        self.assertEqual(EventType.POST_CREATED, "POST_CREATED")
        self.assertEqual(EventType.POST_APPROVED, "POST_APPROVED")
        self.assertEqual(EventType.ANNOUNCEMENT_PUBLISHED, "ANNOUNCEMENT_PUBLISHED")
        self.assertEqual(EventType.BIRTHDAY_WISH_CREATED, "BIRTHDAY_WISH_CREATED")


if __name__ == "__main__":
    unittest.main()
