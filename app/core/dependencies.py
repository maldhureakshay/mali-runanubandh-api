"""
Dependencies module.

Provides FastAPI Dependency Injection providers, such as database sessions,
Firebase authentication validators, and role-based access controllers.
"""

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth as firebase_auth
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.database import db_manager
from app.core.exceptions import UnauthorizedException, ForbiddenException

logger = logging.getLogger(__name__)

# Role Definitions
USER = "USER"
MODERATOR = "MODERATOR"
ADMIN = "ADMIN"
SUPER_ADMIN = "SUPER_ADMIN"

# Security scheme for Firebase ID Tokens passed via Bearer auth header
security_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """
    Model representing the authenticated user context extracted from Firebase custom claims.
    """
    uid: str = Field(..., description="Firebase unique User ID")
    phoneNumber: Optional[str] = Field(None, description="User phone number if available")
    email: Optional[str] = Field(None, description="User email if available")
    name: Optional[str] = Field(None, description="User display name if available")
    roles: List[str] = Field(default_factory=list, description="Assigned authorization roles (e.g. USER, ADMIN)")
    claims: Dict[str, Any] = Field(default_factory=dict, description="Entire decoded token payload")


async def get_db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """
    Dependency provider yielding the initialized async MongoDB database object.
    """
    yield db_manager.get_database()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)
) -> AuthenticatedUser:
    """
    Dependency to authenticate requests using Firebase ID Tokens.
    
    Verifies Bearer token, decodes it, and returns an AuthenticatedUser model.
    """
    if not credentials:
        logger.warning("Authentication failure: Missing Authorization Bearer header.")
        raise UnauthorizedException(message="Missing authentication credentials.")
        
    token = credentials.credentials
    try:
        # Verify the Firebase token
        decoded_token = firebase_auth.verify_id_token(token)
        
        # Extract metadata
        uid = decoded_token.get("uid") or decoded_token.get("sub")
        if not uid:
            logger.warning("Authentication failure: Token missing sub/uid identifier.")
            raise UnauthorizedException(message="Invalid token structure.")

        phone = decoded_token.get("phone_number")
        email = decoded_token.get("email")
        name = decoded_token.get("name")
        
        # Parse roles from custom claims (can be list or string or default to USER)
        raw_roles = decoded_token.get("roles") or decoded_token.get("role")
        roles = []
        if isinstance(raw_roles, list):
            roles = [str(r).upper() for r in raw_roles]
        elif isinstance(raw_roles, str):
            roles = [raw_roles.upper()]
        
        # Standard fallback if no roles mapped
        if not roles:
            roles = [USER]

        logger.info("Authentication success: User %s authenticated with roles: %s", uid, roles)
        
        return AuthenticatedUser(
            uid=uid,
            phoneNumber=phone,
            email=email,
            name=name,
            roles=roles,
            claims=decoded_token
        )
        
    except firebase_auth.ExpiredIdTokenError as e:
        logger.warning("Authentication failure: Firebase token expired: %s", e)
        raise UnauthorizedException(message="Firebase ID Token has expired.")
    except firebase_auth.InvalidIdTokenError as e:
        logger.warning("Authentication failure: Firebase token is invalid: %s", e)
        raise UnauthorizedException(message="Firebase ID Token is invalid.")
    except Exception as e:
        logger.error("Authentication failure: Exception during token validation: %s", e)
        raise UnauthorizedException(message="Could not validate credentials.")


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)
) -> Optional[AuthenticatedUser]:
    """
    Optional dependency to authenticate requests using Firebase ID Tokens.
    Returns None if no credentials are provided or if validation fails.
    """
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except Exception:
        return None



def require_roles(allowed_roles: List[str]):
    """
    Dependency factory ensuring the authenticated user contains at least one of the allowed roles.
    """
    async def role_dependency(
        current_user: AuthenticatedUser = Depends(get_current_user)
    ) -> AuthenticatedUser:
        if not any(role in allowed_roles for role in current_user.roles):
            logger.warning(
                "Authorization failure: User %s (Roles: %s) requested access requiring: %s",
                current_user.uid,
                current_user.roles,
                allowed_roles
            )
            raise ForbiddenException(message="You do not have permission to perform this action.")
        return current_user
        
    return role_dependency


async def get_post_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> Any:
    """
    Dependency provider for PostRepository.
    """
    from app.community.repositories.post import PostRepository
    return PostRepository(db)


async def get_post_review_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> Any:
    """
    Dependency provider for PostReviewRepository.
    """
    from app.community.repositories.review import PostReviewRepository
    return PostReviewRepository(db)


async def get_moderation_dashboard_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> Any:
    """
    Dependency provider for ModerationDashboardRepository.
    """
    from app.community.repositories.dashboard import ModerationDashboardRepository
    return ModerationDashboardRepository(db)


_event_dispatcher = None
_event_bus = None
_event_publisher = None

def get_event_publisher_singleton() -> Any:
    global _event_dispatcher, _event_bus, _event_publisher
    if _event_publisher is None:
        from app.events.event_dispatcher import EventDispatcher
        from app.events.event_bus import EventBus
        from app.events.event_publisher import EventPublisher
        
        _event_dispatcher = EventDispatcher()
        _event_bus = EventBus(_event_dispatcher)
        _event_publisher = EventPublisher(_event_bus)
    return _event_publisher

async def get_event_publisher(publisher = Depends(get_event_publisher_singleton)) -> Any:
    return publisher

async def setup_event_handlers(db: AsyncIOMotorDatabase) -> None:
    global _event_bus
    # Make sure singleton is initialized
    get_event_publisher_singleton()
    
    # Instantiate the services and handlers
    from app.notifications.repositories.notification import NotificationRepository
    from app.notifications.services.notification import NotificationService
    from app.events.handlers.notification_handler import NotificationHandler
    from app.events.handlers.analytics_handler import AnalyticsHandler
    from app.events.handlers.audit_handler import AuditHandler
    from app.events.handlers.search_handler import SearchHandler
    from app.events.handlers.media_handler import MediaHandler
    from app.events.event_types import EventType
    
    notification_repo = NotificationRepository(db)
    notification_service = NotificationService(notification_repo)
    
    notification_handler = NotificationHandler(notification_service, db)
    analytics_handler = AnalyticsHandler()
    audit_handler = AuditHandler()
    search_handler = SearchHandler()
    media_handler = MediaHandler()
    
    # Register handlers on event_bus
    _event_bus.register_handler(EventType.POST_APPROVED, notification_handler)
    _event_bus.register_handler(EventType.POST_REJECTED, notification_handler)
    _event_bus.register_handler(EventType.COMMENT_CREATED, notification_handler)
    _event_bus.register_handler(EventType.POST_LIKED, notification_handler)
    _event_bus.register_handler(EventType.ANNOUNCEMENT_PUBLISHED, notification_handler)
    _event_bus.register_handler(EventType.MARRIAGE_SUCCESS_CREATED, notification_handler)
    
    # Register placeholder handlers for all event types to demonstrate future compatibility
    for et in EventType:
        _event_bus.register_handler(et, analytics_handler)
        _event_bus.register_handler(et, audit_handler)
        _event_bus.register_handler(et, search_handler)
        _event_bus.register_handler(et, media_handler)

async def get_post_review_service(
    review_repo: Any = Depends(get_post_review_repository),
    post_repo: Any = Depends(get_post_repository)
) -> Any:
    """
    Dependency provider for PostReviewService.
    """
    from app.community.services.review import PostReviewService
    return PostReviewService(review_repo, post_repo)


async def get_moderation_dashboard_service(
    dashboard_repo: Any = Depends(get_moderation_dashboard_repository)
) -> Any:
    """
    Dependency provider for ModerationDashboardService.
    """
    from app.community.services.dashboard import ModerationDashboardService
    return ModerationDashboardService(dashboard_repo)


async def get_post_service(
    post_repo: Any = Depends(get_post_repository),
    event_publisher: Any = Depends(get_event_publisher),
    post_review_service: Any = Depends(get_post_review_service)
) -> Any:
    """
    Dependency provider for PostService.
    """
    from app.community.services.post import PostService
    return PostService(post_repo, event_publisher, post_review_service)


async def get_comment_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> Any:
    """
    Dependency provider for CommentRepository.
    """
    from app.community.repositories.comment import CommentRepository
    return CommentRepository(db)


async def get_comment_service(
    comment_repo: Any = Depends(get_comment_repository),
    post_repo: Any = Depends(get_post_repository),
    event_publisher: Any = Depends(get_event_publisher)
) -> Any:
    """
    Dependency provider for CommentService.
    """
    from app.community.services.comment import CommentService
    return CommentService(comment_repo, post_repo, event_publisher)


async def get_like_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> Any:
    """
    Dependency provider for LikeRepository.
    """
    from app.community.repositories.like import LikeRepository
    return LikeRepository(db)


async def get_like_service(
    like_repo: Any = Depends(get_like_repository),
    post_repo: Any = Depends(get_post_repository),
    event_publisher: Any = Depends(get_event_publisher)
) -> Any:
    """
    Dependency provider for LikeService.
    """
    from app.community.services.like import LikeService
    return LikeService(like_repo, post_repo, event_publisher)


async def get_vote_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> Any:
    """
    Dependency provider for VoteRepository.
    """
    from app.community.repositories.vote import VoteRepository
    return VoteRepository(db)


async def get_poll_service(
    vote_repo: Any = Depends(get_vote_repository),
    post_repo: Any = Depends(get_post_repository),
    event_publisher: Any = Depends(get_event_publisher)
) -> Any:
    """
    Dependency provider for PollService.
    """
    from app.community.services.poll import PollService
    return PollService(vote_repo, post_repo, event_publisher)


async def get_report_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> Any:
    """
    Dependency provider for ReportRepository.
    """
    from app.community.repositories.report import ReportRepository
    return ReportRepository(db)


async def get_report_service(
    report_repo: Any = Depends(get_report_repository),
    post_repo: Any = Depends(get_post_repository),
    event_publisher: Any = Depends(get_event_publisher)
) -> Any:
    """
    Dependency provider for ReportService.
    """
    from app.community.services.report import ReportService
    return ReportService(report_repo, post_repo, event_publisher)


async def get_moderation_service(
    post_repo: Any = Depends(get_post_repository),
    event_publisher: Any = Depends(get_event_publisher),
    post_review_service: Any = Depends(get_post_review_service)
) -> Any:
    """
    Dependency provider for ModerationService.
    """
    from app.community.services.moderation import ModerationService
    return ModerationService(post_repo, event_publisher, post_review_service)


async def get_notification_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> Any:
    """
    Dependency provider for NotificationRepository.
    """
    from app.notifications.repositories.notification import NotificationRepository
    return NotificationRepository(db)


async def get_notification_service(
    notification_repo: Any = Depends(get_notification_repository)
) -> Any:
    """
    Dependency provider for NotificationService.
    """
    from app.notifications.services.notification import NotificationService
    return NotificationService(notification_repo)


async def get_marriage_success_service(
    post_repo: Any = Depends(get_post_repository),
    event_publisher: Any = Depends(get_event_publisher),
) -> Any:
    """
    Dependency provider for MarriageSuccessService.
    """
    from app.community.services.marriage import MarriageSuccessService
    return MarriageSuccessService(post_repo, event_publisher)



