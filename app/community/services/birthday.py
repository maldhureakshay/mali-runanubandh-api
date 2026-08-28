import logging
from datetime import datetime, timezone, timedelta
from app.community.models.post import Post, Content, Moderation, AuthorSnapshot, VisibilitySettings, BirthdayMetadata
from app.community.enums import PostType, PostStatus, Visibility
from app.community.repositories.post import PostRepository
from database import db_manager as matrimony_db_manager
from app.community.repositories.exceptions import RepositoryException

logger = logging.getLogger(__name__)


class BirthdayPostService:
    def __init__(self, post_repo: PostRepository) -> None:
        self.post_repo = post_repo

    async def generate_birthday_posts(self) -> int:
        """
        Scan all active & verified profiles in the matrimony database.
        Generate a BIRTHDAY post for anyone whose birthday is today (IST).
        Returns the number of birthday posts successfully created.
        """
        # 1. Get today's month & day in IST
        ist = timezone(timedelta(hours=5, minutes=30))
        today_ist = datetime.now(ist)
        today_month = today_ist.month
        today_day = today_ist.day
        today_date_str = today_ist.strftime("%Y-%m-%d")

        logger.info("Scanning for birthdays today (IST: %s, month: %d, day: %d)", today_date_str, today_month, today_day)

        # 2. Query profiles collection
        profiles_col = matrimony_db_manager.get_collection()
        cursor = profiles_col.find({"active": True, "is_verified": True})
        
        created_count = 0
        system_author = AuthorSnapshot(
            userId="system",
            profileId="system",
            fullName="System",
            verified=True,
            paidMember=True
        )

        async for profile_doc in cursor:
            if not profile_doc.get("active") or not profile_doc.get("is_verified"):
                continue

            birth_date_val = profile_doc.get("birth_date")
            if not birth_date_val:
                continue


            dt = None
            if isinstance(birth_date_val, str):
                try:
                    dt = datetime.fromisoformat(birth_date_val.replace("Z", "+00:00"))
                except Exception:
                    try:
                        dt = datetime.strptime(birth_date_val[:10], "%Y-%m-%d")
                    except Exception:
                        pass
            elif isinstance(birth_date_val, datetime):
                dt = birth_date_val

            if dt is None:
                continue

            # Compare month and day
            if dt.month == today_month and dt.day == today_day:
                profile_id = str(profile_doc.get("_id"))
                full_name = profile_doc.get("full_name") or "Community Member"
                
                # Check for birthday visibility setting if such a setting exists (none exists in schema)
                # Generate deterministic post ID: birthday_YYYYMMDD_profileId
                post_id = f"birthday_{today_ist.strftime('%Y%m%d')}_{profile_id}"
                
                # Check if already exists in DB
                existing = await self.post_repo.collection.find_one({"_id": post_id})
                if existing:
                    logger.info("Birthday post already exists for profileId: %s on %s", profile_id, today_date_str)
                    continue

                # Content
                profile_images = profile_doc.get("images") or []
                content = Content(
                    title="Happy Birthday!",
                    body=f"Wishing {full_name} a very happy birthday!",
                    images=profile_images
                )
                
                # Metadata
                bday_date = datetime(today_ist.year, today_ist.month, today_ist.day, tzinfo=ist)
                metadata = BirthdayMetadata(
                    profileId=profile_id,
                    profileName=full_name,
                    birthdayDate=bday_date
                )
                
                post = Post(
                    id=post_id,
                    type=PostType.BIRTHDAY,
                    author=system_author,
                    content=content,
                    metadata=metadata,
                    moderation=Moderation(
                        status=PostStatus.APPROVED,
                        reviewedAt=datetime.now(timezone.utc),
                        reviewedBy="system",
                        approvalNotes="System generated birthday post"
                    ),
                    visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
                    createdAt=datetime.now(timezone.utc),
                    updatedAt=datetime.now(timezone.utc),
                    publishedAt=datetime.now(timezone.utc)
                )

                try:
                    await self.post_repo.create_post(post)
                    logger.info("Created birthday post for %s (profileId: %s)", full_name, profile_id)
                    created_count += 1
                except Exception as e:
                    err_msg = str(e).lower()
                    if "duplicate key" in err_msg or "e11000" in err_msg:
                        logger.info("Birthday post already exists (write exception) for profileId: %s on %s", profile_id, today_date_str)
                    else:
                        logger.error("Failed to create birthday post for profileId %s: %s", profile_id, e, exc_info=True)

        logger.info("Finished birthday posts generation. Total created: %d", created_count)
        return created_count



