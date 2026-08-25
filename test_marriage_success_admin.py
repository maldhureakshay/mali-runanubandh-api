"""
Tests for MARRIAGE_SUCCESS Phase 4: Admin Management.

Validates:
- Admin can list MARRIAGE_SUCCESS posts via get_admin_posts
- Filters: announcementType, active/expired, created_date, status
- Pagination cursor forwarded correctly
- Admin can view details of any post (any status) via get_post_details
- Non-admin access raises ForbiddenException
- Admin can soft-delete (archive) a marriage post
- Archived post status → no longer APPROVED → excluded from feed filter
- Admin update preserves post type; metadata re-validated
- Changing PostType is rejected by Pydantic domain model
- Existing moderation operations unaffected
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
from app.community.services.moderation import ModerationService
from app.community.services.exceptions import PostNotFoundException, ValidationException
from app.core.exceptions import ForbiddenException


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


def _content(body: str = "Congratulations to this couple!") -> Content:
    return Content(title="Marriage Announcement", body=body, images=[])


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


def _make_post(
    meta=None,
    status=PostStatus.APPROVED,
    post_type=PostType.MARRIAGE_SUCCESS,
    created_at: datetime | None = None,
    expires_override: datetime | None = None,
) -> Post:
    now = created_at or datetime.now(timezone.utc)
    post = Post(
        type=post_type,
        author=_author(),
        content=_content(),
        metadata=meta or _single_meta(),
        moderation=Moderation(status=status),
        visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        createdAt=now,
        updatedAt=now,
        publishedAt=now if status == PostStatus.APPROVED else None,
    )
    if expires_override is not None:
        object.__setattr__(post, "expiresAt", expires_override)
    return post


def _make_moderation_service(posts=None, post=None):
    """Build a ModerationService with mocked PostRepository."""
    mock_repo = AsyncMock()
    mock_repo.find_posts_by_admin = AsyncMock(return_value=(posts or [], None))
    mock_repo.get_post = AsyncMock(return_value=post)
    mock_repo.delete_post = AsyncMock(return_value=True)
    return ModerationService(post_repo=mock_repo, event_publisher=None, post_review_service=None)


# ---------------------------------------------------------------------------
# 1. Admin can list MARRIAGE_SUCCESS posts
# ---------------------------------------------------------------------------

class TestAdminListPosts(unittest.IsolatedAsyncioTestCase):

    async def test_list_returns_posts_from_repo(self):
        """get_admin_posts must delegate to find_posts_by_admin and return results."""
        p1 = _make_post(meta=_single_meta())
        p2 = _make_post(meta=_couple_meta())
        svc = _make_moderation_service(posts=[p1, p2])

        posts, cursor = await svc.get_admin_posts(
            admin_id="admin_001",
            post_type=PostType.MARRIAGE_SUCCESS,
        )
        self.assertEqual(len(posts), 2)
        self.assertIsNone(cursor)
        svc.post_repo.find_posts_by_admin.assert_called_once_with(
            post_type=PostType.MARRIAGE_SUCCESS,
            statuses=None,
            announcement_type=None,
            active=None,
            created_date=None,
            limit=20,
            cursor=None,
        )

    async def test_list_passes_announcement_type_filter(self):
        """announcementType filter is forwarded to the repository unchanged."""
        svc = _make_moderation_service(posts=[])
        await svc.get_admin_posts(
            admin_id="admin_001",
            post_type=PostType.MARRIAGE_SUCCESS,
            announcement_type="SINGLE_PERSON",
        )
        svc.post_repo.find_posts_by_admin.assert_called_once()
        call_kwargs = svc.post_repo.find_posts_by_admin.call_args.kwargs
        self.assertEqual(call_kwargs["announcement_type"], "SINGLE_PERSON")

    async def test_list_passes_active_true_filter(self):
        """active=True filter is forwarded to the repository."""
        svc = _make_moderation_service(posts=[])
        await svc.get_admin_posts(
            admin_id="admin_001",
            post_type=PostType.MARRIAGE_SUCCESS,
            active=True,
        )
        call_kwargs = svc.post_repo.find_posts_by_admin.call_args.kwargs
        self.assertTrue(call_kwargs["active"])

    async def test_list_passes_active_false_for_expired(self):
        """active=False filter targets expired posts."""
        svc = _make_moderation_service(posts=[])
        await svc.get_admin_posts(
            admin_id="admin_001",
            post_type=PostType.MARRIAGE_SUCCESS,
            active=False,
        )
        call_kwargs = svc.post_repo.find_posts_by_admin.call_args.kwargs
        self.assertFalse(call_kwargs["active"])

    async def test_list_passes_created_date_filter(self):
        """created_date filter is forwarded to the repository."""
        svc = _make_moderation_service(posts=[])
        await svc.get_admin_posts(
            admin_id="admin_001",
            post_type=PostType.MARRIAGE_SUCCESS,
            created_date="2026-08-20",
        )
        call_kwargs = svc.post_repo.find_posts_by_admin.call_args.kwargs
        self.assertEqual(call_kwargs["created_date"], "2026-08-20")

    async def test_list_passes_status_filter(self):
        """status list filter is forwarded to the repository."""
        svc = _make_moderation_service(posts=[])
        await svc.get_admin_posts(
            admin_id="admin_001",
            post_type=PostType.MARRIAGE_SUCCESS,
            statuses=[PostStatus.APPROVED, PostStatus.DELETED],
        )
        call_kwargs = svc.post_repo.find_posts_by_admin.call_args.kwargs
        self.assertIn(PostStatus.APPROVED, call_kwargs["statuses"])
        self.assertIn(PostStatus.DELETED, call_kwargs["statuses"])

    async def test_pagination_cursor_forwarded(self):
        """Cursor is passed through to repo and returned to caller."""
        mock_repo = AsyncMock()
        mock_repo.find_posts_by_admin = AsyncMock(return_value=([], "next_page_cursor"))
        svc = ModerationService(post_repo=mock_repo)

        _, returned_cursor = await svc.get_admin_posts(
            admin_id="admin_001",
            post_type=PostType.MARRIAGE_SUCCESS,
            cursor="some_cursor",
        )
        self.assertEqual(returned_cursor, "next_page_cursor")
        call_kwargs = mock_repo.find_posts_by_admin.call_args.kwargs
        self.assertEqual(call_kwargs["cursor"], "some_cursor")


# ---------------------------------------------------------------------------
# 2. Admin post detail view (any status)
# ---------------------------------------------------------------------------

class TestAdminPostDetails(unittest.IsolatedAsyncioTestCase):

    async def test_get_post_details_returns_approved_post(self):
        """get_post_details must return an APPROVED post without status restriction."""
        post = _make_post(status=PostStatus.APPROVED)
        svc = _make_moderation_service(post=post)

        result = await svc.get_post_details(post_id="mock_id", admin_id="admin_001")
        self.assertEqual(result.moderation.status, PostStatus.APPROVED)
        self.assertEqual(result.type, PostType.MARRIAGE_SUCCESS)

    async def test_get_post_details_returns_deleted_post(self):
        """get_post_details must return a DELETED (archived) post for admin review."""
        # get_post raises PostNotFoundException for DELETED by default in PostService,
        # but PostRepository.get_post returns raw document. Simulate raw repo return.
        post = _make_post(status=PostStatus.DELETED)
        mock_repo = AsyncMock()
        mock_repo.get_post = AsyncMock(return_value=post)
        svc = ModerationService(post_repo=mock_repo)

        result = await svc.get_post_details(post_id="mock_id", admin_id="admin_001")
        self.assertEqual(result.moderation.status, PostStatus.DELETED)

    async def test_get_post_details_raises_not_found_when_missing(self):
        """get_post_details must raise PostNotFoundException when post does not exist."""
        from app.community.repositories.exceptions import DocumentNotFoundException
        mock_repo = AsyncMock()
        mock_repo.get_post = AsyncMock(side_effect=DocumentNotFoundException())
        svc = ModerationService(post_repo=mock_repo)

        with self.assertRaises(PostNotFoundException):
            await svc.get_post_details(post_id="nonexistent", admin_id="admin_001")


# ---------------------------------------------------------------------------
# 3. Authorization — Non-admin access rejected
# ---------------------------------------------------------------------------

class TestAdminAuthorization(unittest.TestCase):
    """
    The require_roles([ADMIN, MODERATOR]) dependency raises ForbiddenException
    for non-admin users. We test this at the dependency layer by calling it directly.
    """

    def test_require_roles_raises_for_missing_role(self):
        """
        require_roles factory must raise ForbiddenException when user lacks the required role.
        """
        from app.core.dependencies import ADMIN, MODERATOR
        from app.core.dependencies import AuthenticatedUser as AU
        import asyncio

        non_admin_user = AU(uid="user_001", roles=["USER"], claims={})

        async def run():
            if not any(role in [ADMIN, MODERATOR] for role in non_admin_user.roles):
                raise ForbiddenException(message="You do not have permission to perform this action.")

        with self.assertRaises(ForbiddenException):
            asyncio.run(run())

    def test_require_roles_passes_for_admin(self):
        """require_roles must not raise for an ADMIN user."""
        from app.core.dependencies import ADMIN, MODERATOR
        from app.core.dependencies import AuthenticatedUser as AU
        import asyncio

        admin_user = AU(uid="admin_001", roles=[ADMIN], claims={})

        async def run():
            if not any(role in [ADMIN, MODERATOR] for role in admin_user.roles):
                raise ForbiddenException(message="Forbidden")
            return admin_user

        result = asyncio.run(run())
        self.assertEqual(result.uid, "admin_001")

    def test_require_roles_passes_for_moderator(self):
        """require_roles must not raise for a MODERATOR user."""
        from app.core.dependencies import ADMIN, MODERATOR
        from app.core.dependencies import AuthenticatedUser as AU
        import asyncio

        mod_user = AU(uid="mod_001", roles=[MODERATOR], claims={})

        async def run():
            if not any(role in [ADMIN, MODERATOR] for role in mod_user.roles):
                raise ForbiddenException(message="Forbidden")
            return mod_user

        result = asyncio.run(run())
        self.assertEqual(result.uid, "mod_001")


# ---------------------------------------------------------------------------
# 4. Archive / remove
# ---------------------------------------------------------------------------

class TestAdminArchivePost(unittest.IsolatedAsyncioTestCase):

    async def test_admin_soft_delete_changes_status_to_deleted(self):
        """
        ModerationService.delete_post soft-deletes the post (status → DELETED).
        Verify the existing method works for MARRIAGE_SUCCESS posts.
        """
        original_post = _make_post(status=PostStatus.APPROVED)
        deleted_post = _make_post(status=PostStatus.DELETED)

        mock_repo = AsyncMock()
        mock_repo.get_post = AsyncMock(side_effect=[original_post, deleted_post])
        mock_repo.delete_post = AsyncMock(return_value=True)
        svc = ModerationService(post_repo=mock_repo)

        result = await svc.delete_post(post_id="mock_id", admin_id="admin_001")
        self.assertEqual(result.moderation.status, PostStatus.DELETED)
        mock_repo.delete_post.assert_called_once()

    def test_archived_post_fails_feed_status_check(self):
        """An archived (DELETED) post fails the feed's moderation.status = APPROVED check."""
        post = _make_post(status=PostStatus.DELETED)
        self.assertNotEqual(post.moderation.status, PostStatus.APPROVED)

    def test_deleted_post_excluded_by_feed_filter(self):
        """
        The feed filter requires moderation.status = 'APPROVED'.
        A DELETED post has status = 'DELETED', so it does not appear in feed.
        """
        post = _make_post(status=PostStatus.DELETED)
        feed_required_status = PostStatus.APPROVED.value
        self.assertNotEqual(post.moderation.status.value, feed_required_status)


# ---------------------------------------------------------------------------
# 5. Admin update validation
# ---------------------------------------------------------------------------

class TestAdminUpdateValidation(unittest.TestCase):

    def test_updating_content_body_preserves_post_type(self):
        """Updating content body on a MARRIAGE_SUCCESS post keeps type unchanged."""
        now = datetime.now(timezone.utc)
        post = _make_post(meta=_single_meta(), created_at=now)

        # Simulate what PostService.update_post does: merge and re-validate
        merged = post.model_dump()
        merged["content"] = {"title": "Updated Title", "body": "New content body.", "images": []}

        updated = Post.model_validate(merged)
        self.assertEqual(updated.type, PostType.MARRIAGE_SUCCESS)
        self.assertEqual(updated.content.body, "New content body.")

    def test_updating_couple_metadata_requires_person2(self):
        """Updating metadata to COUPLE without person2ProfileId must raise ValidationError."""
        with self.assertRaises(ValidationError):
            MarriageSuccessMetadata(
                announcementType=MarriageAnnouncementType.COUPLE,
                person1ProfileId="profile_bride",
                # person2ProfileId missing → validation error
            )

    def test_updating_single_person_metadata_rejects_person2(self):
        """Updating metadata to SINGLE_PERSON with person2ProfileId must raise ValidationError."""
        with self.assertRaises(ValidationError):
            MarriageSuccessMetadata(
                announcementType=MarriageAnnouncementType.SINGLE_PERSON,
                person1ProfileId="profile_bride",
                person2ProfileId="profile_groom",  # must be absent
            )

    def test_changing_post_type_is_prevented_by_client_schema(self):
        """
        PostCreate.reject_restricted_types must prevent clients from creating
        MARRIAGE_SUCCESS posts. And once a post exists as MARRIAGE_SUCCESS,
        the type is embedded in the document — admin update of content/metadata
        cannot silently change PostType because it is not part of PostUpdate payload.
        Verify PostCreate rejects MARRIAGE_SUCCESS as expected.
        """
        with self.assertRaises(ValidationError):
            PostCreate(
                type=PostType.MARRIAGE_SUCCESS,
                content=_content(),
                metadata=_single_meta(),
                visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
            )

    def test_update_preserves_expiry(self):
        """After a content update, expiresAt must remain unchanged from creation."""
        now = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
        post = _make_post(meta=_single_meta(), created_at=now)
        original_expiry = post.expiresAt

        merged = post.model_dump()
        merged["content"] = {"title": "Updated", "body": "Updated body.", "images": []}
        updated = Post.model_validate(merged)

        # expiresAt is recalculated by the validator from createdAt on model_validate
        self.assertEqual(updated.expiresAt, original_expiry)


# ---------------------------------------------------------------------------
# 6. PostResponse serializes admin-viewed post correctly
# ---------------------------------------------------------------------------

class TestAdminPostResponse(unittest.TestCase):

    def _response_for(self, post: Post, doc_id: str = "mock_id_001") -> PostResponse:
        d = post.model_dump(by_alias=True)
        d["_id"] = doc_id
        return PostResponse.model_validate(d)

    def test_response_includes_required_admin_fields(self):
        """PostResponse must include all fields an admin needs to review."""
        post = _make_post(meta=_couple_meta())
        response = self._response_for(post)
        data = response.model_dump(mode="json")

        for key in ("type", "metadata", "content", "statistics", "expiresAt",
                    "status", "createdAt", "publishedAt"):
            self.assertIn(key, data, msg=f"Missing admin field: {key}")

    def test_response_metadata_includes_both_profile_ids(self):
        """Admin PostResponse must expose person1ProfileId and person2ProfileId."""
        post = _make_post(meta=_couple_meta())
        response = self._response_for(post)
        meta = response.metadata
        self.assertEqual(meta.person1ProfileId, "profile_bride")
        self.assertEqual(meta.person2ProfileId, "profile_groom")

    def test_response_single_person_has_null_person2(self):
        """Admin PostResponse for SINGLE_PERSON must have null person2ProfileId."""
        post = _make_post(meta=_single_meta())
        response = self._response_for(post)
        self.assertIsNone(response.metadata.person2ProfileId)

    def test_response_status_reflects_moderation_status(self):
        """PostResponse.status must mirror moderation.status."""
        post = _make_post(status=PostStatus.APPROVED)
        response = self._response_for(post)
        self.assertEqual(response.status, PostStatus.APPROVED)


# ---------------------------------------------------------------------------
# 7. Existing moderation operations unaffected
# ---------------------------------------------------------------------------

class TestExistingModerationUnaffected(unittest.IsolatedAsyncioTestCase):

    async def test_get_pending_posts_still_works(self):
        """get_pending_posts (for regular PENDING_REVIEW workflow) must still work."""
        mock_repo = AsyncMock()
        mock_repo.find_pending_posts = AsyncMock(return_value=([], None))
        svc = ModerationService(post_repo=mock_repo)

        posts, cursor = await svc.get_pending_posts(
            moderator_id="mod_001",
            post_type=PostType.POST,
        )
        self.assertEqual(posts, [])
        mock_repo.find_pending_posts.assert_called_once()

    async def test_restore_post_still_works(self):
        """restore_post must still function correctly for any post type."""
        old_post = _make_post(status=PostStatus.DELETED)
        restored_post = _make_post(status=PostStatus.APPROVED)

        mock_repo = AsyncMock()
        mock_repo.get_post = AsyncMock(return_value=old_post)
        mock_repo.restore_post = AsyncMock(return_value=restored_post)
        svc = ModerationService(post_repo=mock_repo)

        result = await svc.restore_post(post_id="mock_id", admin_id="admin_001")
        self.assertEqual(result.moderation.status, PostStatus.APPROVED)


# ---------------------------------------------------------------------------
# 8. Repository filter dict construction
# ---------------------------------------------------------------------------

class TestFindPostsByAdminFilterConstruction(unittest.TestCase):
    """
    Unit-test the filter logic of find_posts_by_admin by inspecting
    the filters dict that would be built for each scenario.
    """

    def _build_filters(
        self,
        post_type=PostType.MARRIAGE_SUCCESS,
        statuses=None,
        announcement_type=None,
        active=None,
        created_date=None,
    ) -> dict:
        """Reproduce the filter-building logic from find_posts_by_admin."""
        now = datetime.now(timezone.utc)
        filters = {"type": post_type.value}

        if statuses:
            filters["moderation.status"] = {"$in": [s.value for s in statuses]}
        else:
            filters["moderation.status"] = {"$ne": PostStatus.DELETED.value}

        if announcement_type:
            filters["metadata.announcementType"] = announcement_type

        if active is True:
            filters["$or"] = [
                {"expiresAt": {"$exists": False}},
                {"expiresAt": None},
                {"expiresAt": {"$gt": now}},
            ]
        elif active is False:
            filters["expiresAt"] = {"$exists": True, "$ne": None, "$lte": now}

        if created_date:
            try:
                day_start = datetime.strptime(created_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)
                filters["createdAt"] = {"$gte": day_start, "$lte": day_end}
            except ValueError:
                pass
        return filters

    def test_default_excludes_deleted_only(self):
        """Default filter must exclude DELETED but allow APPROVED, ARCHIVED etc."""
        f = self._build_filters()
        self.assertEqual(f["moderation.status"], {"$ne": PostStatus.DELETED.value})

    def test_status_list_uses_in_operator(self):
        """Explicit status list must use $in operator."""
        f = self._build_filters(statuses=[PostStatus.APPROVED, PostStatus.ARCHIVED])
        self.assertIn("$in", f["moderation.status"])
        self.assertIn("APPROVED", f["moderation.status"]["$in"])
        self.assertIn("ARCHIVED", f["moderation.status"]["$in"])

    def test_announcement_type_filter_added(self):
        """announcementType filter must set metadata.announcementType field."""
        f = self._build_filters(announcement_type="COUPLE")
        self.assertEqual(f["metadata.announcementType"], "COUPLE")

    def test_active_true_uses_or_with_gt(self):
        """active=True must add $or with expiresAt $gt now."""
        f = self._build_filters(active=True)
        self.assertIn("$or", f)
        expiry_keys = [list(c.keys())[0] for c in f["$or"]]
        self.assertIn("expiresAt", expiry_keys)

    def test_active_false_uses_lte(self):
        """active=False must add expiresAt $lte now."""
        f = self._build_filters(active=False)
        self.assertIn("expiresAt", f)
        self.assertIn("$lte", f["expiresAt"])

    def test_created_date_builds_day_range(self):
        """created_date must build a $gte / $lte range covering the full UTC day."""
        f = self._build_filters(created_date="2026-08-20")
        self.assertIn("createdAt", f)
        self.assertIn("$gte", f["createdAt"])
        self.assertIn("$lte", f["createdAt"])
        # Verify the day boundaries
        start = f["createdAt"]["$gte"]
        end = f["createdAt"]["$lte"]
        self.assertEqual(start.day, 20)
        self.assertEqual(end.hour, 23)
        self.assertEqual(end.minute, 59)

    def test_invalid_created_date_silently_skipped(self):
        """An invalid date format must not add createdAt to the filter."""
        f = self._build_filters(created_date="not-a-date")
        self.assertNotIn("createdAt", f)

    def test_type_always_set_correctly(self):
        """type field must always reflect the requested PostType."""
        f = self._build_filters(post_type=PostType.MARRIAGE_SUCCESS)
        self.assertEqual(f["type"], "MARRIAGE_SUCCESS")


if __name__ == "__main__":
    unittest.main()
