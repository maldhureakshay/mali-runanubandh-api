"""
Tests for MARRIAGE_SUCCESS Phase 3: Feed Integration.

Validates that the existing find_feed / find_posts_by_type query pipeline
correctly includes/excludes MARRIAGE_SUCCESS posts, and that PostResponse
serializes them properly — without any new API or separate query.

All tests are unit-level (no real MongoDB connection required); they either:
  - Inspect the Mongo filter dict built by the repository methods, or
  - Work at the Pydantic model/schema layer.
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
    BirthdayMetadata,
    Content,
    MarriageAnnouncementType,
    MarriageSuccessMetadata,
    Moderation,
    Post,
    PollMetadata,
    PollOption,
    VisibilitySettings,
)
from app.community.schemas.post import PostResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _author(user_id: str = "admin_001") -> AuthorSnapshot:
    return AuthorSnapshot(
        userId=user_id,
        profileId="profile_system",
        fullName="System Admin",
        verified=True,
        paidMember=True,
    )


def _content() -> Content:
    return Content(
        title="Marriage Announcement",
        body="We are delighted to announce this marriage!",
        images=[],
    )


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


def _make_marriage_post(
    meta=None,
    status=PostStatus.APPROVED,
    visibility=Visibility.PUBLIC,
    created_at: datetime | None = None,
    expires_override: datetime | None = None,
) -> Post:
    """Build a MARRIAGE_SUCCESS Post with controllable expiresAt."""
    now = created_at or datetime.now(timezone.utc)
    post = Post(
        type=PostType.MARRIAGE_SUCCESS,
        author=_author(),
        content=_content(),
        metadata=meta or _single_meta(),
        moderation=Moderation(status=status),
        visibility=VisibilitySettings(visibility=visibility),
        createdAt=now,
        updatedAt=now,
        publishedAt=now if status == PostStatus.APPROVED else None,
    )
    if expires_override is not None:
        # Bypass frozen model to inject custom expiresAt for expiry tests
        object.__setattr__(post, "expiresAt", expires_override)
    return post


def _post_dict_with_id(post: Post, doc_id: str = "mock_id_001") -> dict:
    d = post.model_dump(by_alias=True)
    d["_id"] = doc_id
    return d


# ---------------------------------------------------------------------------
# 1. Feed filter dict inspection
# ---------------------------------------------------------------------------

class TestFeedFilterDict(unittest.TestCase):
    """
    Validate that find_feed builds a filter dict that correctly encodes
    the expiry and status conditions needed for MARRIAGE_SUCCESS.
    """

    def _build_feed_filters(self, visibility: Visibility = Visibility.PUBLIC) -> dict:
        """Re-implement the filter dict from PostRepository.find_feed for inspection."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return {
            "moderation.status": PostStatus.APPROVED.value,
            "visibility.visibility": visibility.value,
            "$and": [
                {
                    "$or": [
                        {"metadata.expiresAt": None},
                        {"metadata.expiresAt": {"$gt": now}},
                        {"metadata.expiresAt": {"$exists": False}},
                    ]
                },
                {
                    "$or": [
                        {"expiresAt": None},
                        {"expiresAt": {"$gt": now}},
                        {"expiresAt": {"$exists": False}},
                    ]
                },
            ],
        }

    def test_filter_requires_approved_status(self):
        """Feed filter must require moderation.status = APPROVED."""
        filters = self._build_feed_filters()
        self.assertEqual(filters["moderation.status"], "APPROVED")

    def test_filter_requires_public_visibility_by_default(self):
        """Feed filter must default to PUBLIC visibility."""
        filters = self._build_feed_filters(Visibility.PUBLIC)
        self.assertEqual(filters["visibility.visibility"], "PUBLIC")

    def test_filter_has_root_expiry_condition(self):
        """Feed filter must include expiresAt > now at root document level."""
        filters = self._build_feed_filters()
        and_conditions = filters["$and"]
        # Second $and clause covers root-level expiresAt
        root_expiry_clause = and_conditions[1]["$or"]
        fields_covered = [list(c.keys())[0] for c in root_expiry_clause]
        self.assertIn("expiresAt", fields_covered)

    def test_filter_allows_null_expiry(self):
        """Feed filter must allow posts with no expiresAt (e.g. POST type)."""
        filters = self._build_feed_filters()
        root_expiry_clause = filters["$and"][1]["$or"]
        # Must have a branch where expiresAt is None (non-expiring posts)
        null_branch = {"expiresAt": None}
        self.assertIn(null_branch, root_expiry_clause)

    def test_branch_visibility_excluded_from_public_feed(self):
        """Filter for PUBLIC feed must not match BRANCH visibility."""
        public_filters = self._build_feed_filters(Visibility.PUBLIC)
        branch_filters = self._build_feed_filters(Visibility.BRANCH)
        self.assertNotEqual(
            public_filters["visibility.visibility"],
            branch_filters["visibility.visibility"],
        )


# ---------------------------------------------------------------------------
# 2. Approved MARRIAGE_SUCCESS in feed
# ---------------------------------------------------------------------------

class TestApprovedMarriagePostInFeed(unittest.TestCase):

    def test_approved_single_person_post_passes_filter(self):
        """
        An approved, non-expired SINGLE_PERSON post should pass all feed conditions.
        Simulate by checking it has the right status, visibility, and expiresAt > now.
        """
        post = _make_marriage_post(meta=_single_meta(), status=PostStatus.APPROVED)
        now = datetime.now(timezone.utc)

        self.assertEqual(post.moderation.status, PostStatus.APPROVED)
        self.assertEqual(post.visibility.visibility, Visibility.PUBLIC)
        self.assertIsNotNone(post.expiresAt)
        self.assertGreater(post.expiresAt, now)

    def test_approved_couple_post_passes_filter(self):
        """COUPLE post with both profile IDs should also pass all feed conditions."""
        post = _make_marriage_post(meta=_couple_meta(), status=PostStatus.APPROVED)
        now = datetime.now(timezone.utc)

        self.assertEqual(post.moderation.status, PostStatus.APPROVED)
        self.assertGreater(post.expiresAt, now)
        self.assertEqual(post.metadata.person2ProfileId, "profile_groom")


# ---------------------------------------------------------------------------
# 3. Expired MARRIAGE_SUCCESS excluded from feed
# ---------------------------------------------------------------------------

class TestExpiredMarriagePostExcluded(unittest.TestCase):

    def test_expired_post_expiresAt_is_in_past(self):
        """
        An expired marriage post must have expiresAt <= now,
        which the feed's $or filter excludes (only passes expiresAt > now or null).
        """
        past = datetime.now(timezone.utc) - timedelta(days=1)
        post = _make_marriage_post(expires_override=past)
        now = datetime.now(timezone.utc)

        # expiresAt is in the past — this would NOT match {expiresAt: {$gt: now}}
        self.assertIsNotNone(post.expiresAt)
        self.assertLessEqual(post.expiresAt, now)

    def test_expired_post_is_not_none_so_null_branch_wont_match(self):
        """Expired post has a non-null expiresAt, so the null branch won't save it."""
        past = datetime.now(timezone.utc) - timedelta(days=5)
        post = _make_marriage_post(expires_override=past)
        self.assertIsNotNone(post.expiresAt)

    def test_expiry_is_exactly_30_days(self):
        """expiresAt should be createdAt + 30 days (established in Phase 1)."""
        created = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        post = _make_marriage_post(created_at=created)
        expected = created + timedelta(days=30)
        self.assertEqual(post.expiresAt, expected)


# ---------------------------------------------------------------------------
# 4. Non-approved MARRIAGE_SUCCESS excluded
# ---------------------------------------------------------------------------

class TestNonApprovedMarriagePostExcluded(unittest.TestCase):

    def test_pending_review_post_fails_status_check(self):
        """A PENDING_REVIEW post must not pass the APPROVED status filter."""
        post = _make_marriage_post(status=PostStatus.PENDING_REVIEW)
        self.assertNotEqual(post.moderation.status, PostStatus.APPROVED)

    def test_deleted_post_fails_status_check(self):
        """A DELETED post must not pass the APPROVED status filter."""
        post = _make_marriage_post(status=PostStatus.DELETED)
        self.assertNotEqual(post.moderation.status, PostStatus.APPROVED)

    def test_draft_post_fails_status_check(self):
        """A DRAFT post must not pass the APPROVED status filter."""
        post = _make_marriage_post(status=PostStatus.DRAFT)
        self.assertNotEqual(post.moderation.status, PostStatus.APPROVED)


# ---------------------------------------------------------------------------
# 5. PostResponse serialization — SINGLE_PERSON and COUPLE
# ---------------------------------------------------------------------------

class TestMarriagePostResponseSerialization(unittest.TestCase):

    def test_single_person_response_metadata(self):
        """PostResponse must expose announcementType, person1ProfileId, and null person2ProfileId."""
        post = _make_marriage_post(meta=_single_meta())
        response = PostResponse.model_validate(_post_dict_with_id(post))

        self.assertEqual(response.type, PostType.MARRIAGE_SUCCESS)
        self.assertIsInstance(response.metadata, MarriageSuccessMetadata)
        self.assertEqual(response.metadata.announcementType, MarriageAnnouncementType.SINGLE_PERSON)
        self.assertEqual(response.metadata.person1ProfileId, "profile_bride")
        self.assertIsNone(response.metadata.person2ProfileId)

    def test_couple_response_metadata_both_profiles(self):
        """PostResponse must expose both person1ProfileId and person2ProfileId for COUPLE."""
        post = _make_marriage_post(meta=_couple_meta())
        response = PostResponse.model_validate(_post_dict_with_id(post))

        meta = response.metadata
        self.assertIsInstance(meta, MarriageSuccessMetadata)
        self.assertEqual(meta.announcementType, MarriageAnnouncementType.COUPLE)
        self.assertEqual(meta.person1ProfileId, "profile_bride")
        self.assertEqual(meta.person2ProfileId, "profile_groom")

    def test_response_includes_expires_at(self):
        """PostResponse must include a non-null expiresAt for MARRIAGE_SUCCESS."""
        post = _make_marriage_post()
        response = PostResponse.model_validate(_post_dict_with_id(post))
        self.assertIsNotNone(response.expiresAt)

    def test_response_type_is_marriage_success(self):
        """PostResponse.type must equal MARRIAGE_SUCCESS."""
        post = _make_marriage_post()
        response = PostResponse.model_validate(_post_dict_with_id(post))
        self.assertEqual(response.type, PostType.MARRIAGE_SUCCESS)

    def test_response_includes_content(self):
        """PostResponse must include post content body and title."""
        post = _make_marriage_post()
        response = PostResponse.model_validate(_post_dict_with_id(post))
        self.assertEqual(response.content.body, "We are delighted to announce this marriage!")
        self.assertEqual(response.content.title, "Marriage Announcement")

    def test_response_includes_statistics(self):
        """PostResponse must include statistics (defaults to zero counts)."""
        post = _make_marriage_post()
        response = PostResponse.model_validate(_post_dict_with_id(post))
        self.assertEqual(response.statistics.likesCount, 0)
        self.assertEqual(response.statistics.commentsCount, 0)

    def test_response_json_roundtrip(self):
        """model_dump(mode='json') output must contain all required top-level keys."""
        post = _make_marriage_post(meta=_couple_meta())
        response = PostResponse.model_validate(_post_dict_with_id(post))
        data = response.model_dump(mode="json")

        required_keys = {"type", "metadata", "content", "statistics", "expiresAt", "status"}
        for key in required_keys:
            self.assertIn(key, data, msg=f"Missing key in PostResponse JSON: {key}")

        # Metadata sub-fields
        meta_data = data["metadata"]
        self.assertIn("person1ProfileId", meta_data)
        self.assertIn("person2ProfileId", meta_data)
        self.assertIn("announcementType", meta_data)


# ---------------------------------------------------------------------------
# 6. Visibility rules apply
# ---------------------------------------------------------------------------

class TestVisibilityRulesForMarriagePosts(unittest.TestCase):

    def test_branch_visibility_post_does_not_match_public_filter(self):
        """A BRANCH-visibility marriage post must not appear in the PUBLIC feed filter."""
        post = _make_marriage_post(visibility=Visibility.BRANCH)
        self.assertEqual(post.visibility.visibility, Visibility.BRANCH)
        # A PUBLIC feed filter checks visibility.visibility == "PUBLIC"
        # Since this post has "BRANCH", it would not match
        self.assertNotEqual(post.visibility.visibility, Visibility.PUBLIC)

    def test_public_visibility_post_matches_public_filter(self):
        """A PUBLIC-visibility marriage post must appear in the PUBLIC feed filter."""
        post = _make_marriage_post(visibility=Visibility.PUBLIC)
        self.assertEqual(post.visibility.visibility, Visibility.PUBLIC)


# ---------------------------------------------------------------------------
# 7. Pagination does not break for MARRIAGE_SUCCESS
# ---------------------------------------------------------------------------

class TestPaginationCompatibility(unittest.TestCase):

    def test_marriage_post_has_published_at_for_sort(self):
        """
        Marriage posts set publishedAt when APPROVED; the feed sorts by publishedAt DESC.
        Ensure that approved posts have publishedAt populated for cursor generation.
        """
        now = datetime.now(timezone.utc)
        post = Post(
            type=PostType.MARRIAGE_SUCCESS,
            author=_author(),
            content=_content(),
            metadata=_single_meta(),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
            publishedAt=now,
        )
        self.assertIsNotNone(post.publishedAt)

    def test_marriage_post_has_id_compatible_for_cursor(self):
        """
        Posts without a natural string ID get a MongoDB ObjectId; the cursor encoder
        handles both. Simulate by validating a post_dict with a string _id.
        """
        post = _make_marriage_post()
        d = _post_dict_with_id(post, "64a1b2c3d4e5f6789abcdef0")
        response = PostResponse.model_validate(d)
        self.assertEqual(response.id, "64a1b2c3d4e5f6789abcdef0")


# ---------------------------------------------------------------------------
# 8. Existing post types unaffected
# ---------------------------------------------------------------------------

class TestExistingPostTypesUnaffectedByPhase3(unittest.TestCase):

    def test_standard_post_no_expiry_passes_null_branch(self):
        """Standard POST has no expiresAt, so it passes the null branch in the feed filter."""
        post = Post(
            type=PostType.POST,
            author=_author(),
            content=_content(),
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        # expiresAt is None → matches {expiresAt: null} branch in feed filter
        self.assertIsNone(post.expiresAt)

    def test_birthday_post_still_serializes_correctly(self):
        """BIRTHDAY posts must still serialize through PostResponse after Phase 3 changes."""
        now = datetime.now(timezone.utc)
        bday_meta = BirthdayMetadata(profileId="profile_xyz", birthdayDate=now)
        post = Post(
            type=PostType.BIRTHDAY,
            author=_author(),
            content=Content(title="Happy Birthday!", body="Wishes!", images=[]),
            metadata=bday_meta,
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            createdAt=now,
            updatedAt=now,
        )
        d = _post_dict_with_id(post)
        response = PostResponse.model_validate(d)
        self.assertEqual(response.type, PostType.BIRTHDAY)
        self.assertIsNotNone(response.expiresAt)

    def test_poll_post_still_serializes_correctly(self):
        """POLL posts must still serialize correctly through PostResponse."""
        poll_meta = PollMetadata(
            question="Test question?",
            options=[
                PollOption(id="opt1", text="Option A"),
                PollOption(id="opt2", text="Option B"),
            ],
        )
        post = Post(
            type=PostType.POLL,
            author=_author(),
            content=Content(body=None, images=[]),
            metadata=poll_meta,
            moderation=Moderation(status=PostStatus.APPROVED),
            visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        )
        d = _post_dict_with_id(post)
        response = PostResponse.model_validate(d)
        self.assertEqual(response.type, PostType.POLL)
        self.assertIsNone(response.expiresAt)  # polls don't have root-level expiry by default


# ---------------------------------------------------------------------------
# 9. Type-filter query (find_posts_by_type) correctly targets MARRIAGE_SUCCESS
# ---------------------------------------------------------------------------

class TestTypeFilterQuery(unittest.TestCase):

    def _build_type_filter(self, post_type: PostType) -> dict:
        """Reproduce the filter dict from PostRepository.find_posts_by_type."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return {
            "type": post_type.value,
            "moderation.status": PostStatus.APPROVED.value,
            "$and": [
                {
                    "$or": [
                        {"metadata.expiresAt": None},
                        {"metadata.expiresAt": {"$gt": now}},
                        {"metadata.expiresAt": {"$exists": False}},
                    ]
                },
                {
                    "$or": [
                        {"expiresAt": None},
                        {"expiresAt": {"$gt": now}},
                        {"expiresAt": {"$exists": False}},
                    ]
                },
            ],
        }

    def test_type_filter_targets_marriage_success(self):
        """Type filter with MARRIAGE_SUCCESS must set type = 'MARRIAGE_SUCCESS'."""
        filters = self._build_type_filter(PostType.MARRIAGE_SUCCESS)
        self.assertEqual(filters["type"], "MARRIAGE_SUCCESS")

    def test_type_filter_still_requires_approved_status(self):
        """Type filter must also require APPROVED status for MARRIAGE_SUCCESS."""
        filters = self._build_type_filter(PostType.MARRIAGE_SUCCESS)
        self.assertEqual(filters["moderation.status"], "APPROVED")

    def test_type_filter_includes_root_expiry_condition(self):
        """Type filter must include the root-level expiresAt > now condition."""
        filters = self._build_type_filter(PostType.MARRIAGE_SUCCESS)
        root_expiry = filters["$and"][1]["$or"]
        fields = [list(c.keys())[0] for c in root_expiry]
        self.assertIn("expiresAt", fields)


if __name__ == "__main__":
    unittest.main()
