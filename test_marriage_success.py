"""
Tests for MARRIAGE_SUCCESS PostType — Phase 1.

Covers:
- Enum value existence
- MarriageAnnouncementType values
- MarriageSuccessMetadata: valid SINGLE_PERSON and COUPLE
- MarriageSuccessMetadata: invalid combinations
- Post model: valid MARRIAGE_SUCCESS + expiresAt = createdAt + 30 days
- Post model: wrong metadata type raises ValidationError
- PostResponse: serializes MARRIAGE_SUCCESS + metadata + expiresAt
- PostCreate: rejects MARRIAGE_SUCCESS from clients
- Existing post types unaffected
"""

import sys
import unittest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError

sys.path.append("/Users/akshaykumarmaldhure/work/matrimony-api")

from app.community.enums import PostType, PostStatus, Visibility
from app.community.models.post import (
    AuthorSnapshot,
    BirthdayMetadata,
    Content,
    HelpRequestMetadata,
    MarriageAnnouncementType,
    MarriageSuccessMetadata,
    Moderation,
    Post,
    VisibilitySettings,
)
from app.community.schemas.post import PostCreate, PostResponse


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _author() -> AuthorSnapshot:
    return AuthorSnapshot(
        userId="admin_001",
        profileId="profile_system",
        fullName="System Admin",
        verified=True,
        paidMember=True,
    )


def _content(body: str = "We are delighted to announce this marriage!") -> Content:
    return Content(title="Marriage Announcement", body=body, images=[])


def _single_metadata() -> MarriageSuccessMetadata:
    return MarriageSuccessMetadata(
        announcementType=MarriageAnnouncementType.SINGLE_PERSON,
        person1ProfileId="profile_abc",
    )


def _couple_metadata() -> MarriageSuccessMetadata:
    return MarriageSuccessMetadata(
        announcementType=MarriageAnnouncementType.COUPLE,
        person1ProfileId="profile_abc",
        person2ProfileId="profile_xyz",
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestMarriageSuccessEnum(unittest.TestCase):

    def test_marriage_success_enum_exists(self):
        """MARRIAGE_SUCCESS must be a valid PostType value."""
        self.assertEqual(PostType.MARRIAGE_SUCCESS, "MARRIAGE_SUCCESS")

    def test_marriage_success_enum_is_string(self):
        """PostType inherits from str, so the value must behave as a string."""
        self.assertIsInstance(PostType.MARRIAGE_SUCCESS, str)

    def test_existing_post_types_unaffected(self):
        """Adding MARRIAGE_SUCCESS must not alter any existing PostType values."""
        self.assertEqual(PostType.POST, "POST")
        self.assertEqual(PostType.SUCCESS_STORY, "SUCCESS_STORY")
        self.assertEqual(PostType.POLL, "POLL")
        self.assertEqual(PostType.HELP_REQUEST, "HELP_REQUEST")
        self.assertEqual(PostType.ANNOUNCEMENT, "ANNOUNCEMENT")
        self.assertEqual(PostType.BIRTHDAY, "BIRTHDAY")


class TestMarriageAnnouncementType(unittest.TestCase):

    def test_single_person_value(self):
        self.assertEqual(MarriageAnnouncementType.SINGLE_PERSON, "SINGLE_PERSON")

    def test_couple_value(self):
        self.assertEqual(MarriageAnnouncementType.COUPLE, "COUPLE")


class TestMarriageSuccessMetadata(unittest.TestCase):

    def test_valid_single_person_no_person2(self):
        """SINGLE_PERSON with no person2ProfileId must succeed."""
        meta = MarriageSuccessMetadata(
            announcementType=MarriageAnnouncementType.SINGLE_PERSON,
            person1ProfileId="profile_abc",
        )
        self.assertEqual(meta.announcementType, MarriageAnnouncementType.SINGLE_PERSON)
        self.assertEqual(meta.person1ProfileId, "profile_abc")
        self.assertIsNone(meta.person2ProfileId)

    def test_valid_single_person_explicit_none(self):
        """SINGLE_PERSON with person2ProfileId=None explicitly must succeed."""
        meta = MarriageSuccessMetadata(
            announcementType=MarriageAnnouncementType.SINGLE_PERSON,
            person1ProfileId="profile_abc",
            person2ProfileId=None,
        )
        self.assertIsNone(meta.person2ProfileId)

    def test_valid_couple_both_ids(self):
        """COUPLE with both IDs present must succeed."""
        meta = MarriageSuccessMetadata(
            announcementType=MarriageAnnouncementType.COUPLE,
            person1ProfileId="profile_abc",
            person2ProfileId="profile_xyz",
        )
        self.assertEqual(meta.person1ProfileId, "profile_abc")
        self.assertEqual(meta.person2ProfileId, "profile_xyz")

    def test_single_person_with_person2_raises(self):
        """SINGLE_PERSON with a non-null person2ProfileId must raise ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            MarriageSuccessMetadata(
                announcementType=MarriageAnnouncementType.SINGLE_PERSON,
                person1ProfileId="profile_abc",
                person2ProfileId="profile_xyz",
            )
        self.assertIn("person2ProfileId must be null/absent", str(ctx.exception))

    def test_couple_missing_person2_raises(self):
        """COUPLE with no person2ProfileId must raise ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            MarriageSuccessMetadata(
                announcementType=MarriageAnnouncementType.COUPLE,
                person1ProfileId="profile_abc",
            )
        self.assertIn("person2ProfileId is required", str(ctx.exception))

    def test_couple_empty_string_person2_raises(self):
        """COUPLE with an empty-string person2ProfileId must raise ValidationError."""
        with self.assertRaises(ValidationError):
            MarriageSuccessMetadata(
                announcementType=MarriageAnnouncementType.COUPLE,
                person1ProfileId="profile_abc",
                person2ProfileId="   ",
            )

    def test_missing_person1_raises(self):
        """Missing person1ProfileId must raise ValidationError."""
        with self.assertRaises(ValidationError):
            MarriageSuccessMetadata(
                announcementType=MarriageAnnouncementType.SINGLE_PERSON,
            )


class TestMarriageSuccessPostModel(unittest.TestCase):

    def test_valid_single_person_post(self):
        """Post with MARRIAGE_SUCCESS + SINGLE_PERSON metadata must be created."""
        now = datetime.now(timezone.utc)
        post = Post(
            type=PostType.MARRIAGE_SUCCESS,
            author=_author(),
            content=_content(),
            metadata=_single_metadata(),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
        )
        self.assertEqual(post.type, PostType.MARRIAGE_SUCCESS)
        self.assertIsInstance(post.metadata, MarriageSuccessMetadata)
        self.assertEqual(post.metadata.announcementType, MarriageAnnouncementType.SINGLE_PERSON)

    def test_valid_couple_post(self):
        """Post with MARRIAGE_SUCCESS + COUPLE metadata must be created."""
        now = datetime.now(timezone.utc)
        post = Post(
            type=PostType.MARRIAGE_SUCCESS,
            author=_author(),
            content=_content(),
            metadata=_couple_metadata(),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
        )
        self.assertIsInstance(post.metadata, MarriageSuccessMetadata)
        self.assertEqual(post.metadata.announcementType, MarriageAnnouncementType.COUPLE)
        self.assertEqual(post.metadata.person2ProfileId, "profile_xyz")

    def test_expires_at_is_30_days_from_created_at(self):
        """expiresAt must be exactly createdAt + 30 days."""
        now = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
        post = Post(
            type=PostType.MARRIAGE_SUCCESS,
            author=_author(),
            content=_content(),
            metadata=_single_metadata(),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
        )
        expected_expiry = now + timedelta(days=30)
        self.assertIsNotNone(post.expiresAt)
        self.assertEqual(post.expiresAt, expected_expiry)

    def test_expires_at_naive_datetime_handled(self):
        """If createdAt is timezone-naive, expiresAt must still be set correctly."""
        naive_now = datetime(2026, 8, 20, 10, 0, 0)  # no tzinfo
        post = Post(
            type=PostType.MARRIAGE_SUCCESS,
            author=_author(),
            content=_content(),
            metadata=_single_metadata(),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=naive_now,
            updatedAt=naive_now,
        )
        self.assertIsNotNone(post.expiresAt)
        expected = naive_now.replace(tzinfo=timezone.utc) + timedelta(days=30)
        self.assertEqual(post.expiresAt, expected)

    def test_wrong_metadata_type_raises(self):
        """Supplying BirthdayMetadata for a MARRIAGE_SUCCESS post must raise ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            Post(
                type=PostType.MARRIAGE_SUCCESS,
                author=_author(),
                content=_content(),
                metadata=BirthdayMetadata(profileName="Test User", profileId="profile_abc",
                    birthdayDate=datetime.now(timezone.utc),
                ),
                moderation=Moderation(status=PostStatus.APPROVED),
                visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            )
        self.assertIn("MarriageSuccessMetadata", str(ctx.exception))

    def test_missing_metadata_raises(self):
        """MARRIAGE_SUCCESS with no metadata must raise ValidationError."""
        with self.assertRaises(ValidationError):
            Post(
                type=PostType.MARRIAGE_SUCCESS,
                author=_author(),
                content=_content(),
                metadata=None,
                moderation=Moderation(status=PostStatus.APPROVED),
                visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            )


class TestMarriageSuccessPostResponse(unittest.TestCase):

    def test_post_response_serialization_single_person(self):
        """PostResponse must correctly serialize a MARRIAGE_SUCCESS SINGLE_PERSON post."""
        now = datetime.now(timezone.utc)
        post = Post(
            type=PostType.MARRIAGE_SUCCESS,
            author=_author(),
            content=_content(),
            metadata=_single_metadata(),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
        )
        post_dict = post.model_dump(by_alias=True)
        post_dict["_id"] = "mock_object_id_001"

        response = PostResponse.model_validate(post_dict)
        self.assertEqual(response.type, PostType.MARRIAGE_SUCCESS)
        self.assertIsInstance(response.metadata, MarriageSuccessMetadata)
        self.assertEqual(response.metadata.announcementType, MarriageAnnouncementType.SINGLE_PERSON)
        self.assertIsNotNone(response.expiresAt)
        self.assertEqual(response.expiresAt, now + timedelta(days=30))

    def test_post_response_serialization_couple(self):
        """PostResponse must correctly serialize a MARRIAGE_SUCCESS COUPLE post."""
        now = datetime.now(timezone.utc)
        post = Post(
            type=PostType.MARRIAGE_SUCCESS,
            author=_author(),
            content=_content(),
            metadata=_couple_metadata(),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
        )
        post_dict = post.model_dump(by_alias=True)
        post_dict["_id"] = "mock_object_id_002"

        response = PostResponse.model_validate(post_dict)
        self.assertEqual(response.type, PostType.MARRIAGE_SUCCESS)
        meta = response.metadata
        self.assertIsInstance(meta, MarriageSuccessMetadata)
        self.assertEqual(meta.person1ProfileId, "profile_abc")
        self.assertEqual(meta.person2ProfileId, "profile_xyz")

    def test_post_response_json_roundtrip(self):
        """model_dump(mode='json') must produce valid JSON-serializable output."""
        now = datetime.now(timezone.utc)
        post = Post(
            type=PostType.MARRIAGE_SUCCESS,
            author=_author(),
            content=_content(),
            metadata=_single_metadata(),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
        )
        post_dict = post.model_dump(by_alias=True)
        post_dict["_id"] = "mock_object_id_003"

        response = PostResponse.model_validate(post_dict)
        serialized = response.model_dump(mode="json")
        self.assertEqual(serialized["type"], "MARRIAGE_SUCCESS")
        self.assertIn("expiresAt", serialized)
        self.assertIsNotNone(serialized["expiresAt"])


class TestPostCreateRejectsMarriageSuccess(unittest.TestCase):

    def test_client_cannot_create_marriage_success(self):
        """PostCreate must reject MARRIAGE_SUCCESS with a descriptive error."""
        with self.assertRaises(ValidationError) as ctx:
            PostCreate(
                type=PostType.MARRIAGE_SUCCESS,
                content=_content(),
                metadata=_single_metadata(),
                visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            )
        self.assertIn(
            "Marriage success posts cannot be created by clients directly.",
            str(ctx.exception),
        )

    def test_client_cannot_create_birthday(self):
        """Existing BIRTHDAY rejection must still work after the refactor."""
        with self.assertRaises(ValidationError) as ctx:
            PostCreate(
                type=PostType.BIRTHDAY,
                content=_content(),
                metadata=BirthdayMetadata(profileName="Test User", profileId="profile_abc",
                    birthdayDate=datetime.now(timezone.utc),
                ),
                visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            )
        self.assertIn("Birthday posts cannot be created by clients directly.", str(ctx.exception))

    def test_normal_post_type_still_accepted(self):
        """Regular POST type must still be accepted by PostCreate."""
        pc = PostCreate(
            type=PostType.POST,
            content=_content(),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        self.assertEqual(pc.type, PostType.POST)

    def test_success_story_still_accepted(self):
        """SUCCESS_STORY type must still be accepted by PostCreate."""
        pc = PostCreate(
            type=PostType.SUCCESS_STORY,
            content=_content(),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        self.assertEqual(pc.type, PostType.SUCCESS_STORY)


class TestExistingPostTypesUnaffected(unittest.TestCase):
    """Regression: ensure existing post-type validation paths are not broken."""

    def test_normal_post_model_no_expiry(self):
        """Standard POST type must not receive an expiresAt."""
        post = Post(
            type=PostType.POST,
            author=_author(),
            content=_content(),
            moderation=Moderation(status=PostStatus.PENDING_REVIEW),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        self.assertIsNone(post.expiresAt)

    def test_help_request_model_still_valid(self):
        """HELP_REQUEST posts must still be constructed without errors."""
        post = Post(
            type=PostType.HELP_REQUEST,
            author=_author(),
            content=_content(),
            metadata=HelpRequestMetadata(urgent=True),
            moderation=Moderation(status=PostStatus.PENDING_REVIEW),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        self.assertEqual(post.type, PostType.HELP_REQUEST)


if __name__ == "__main__":
    unittest.main()
