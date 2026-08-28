"""
Routers subpackage for the Community Service module.

Exposes a unified router including all post, comment, like, and report endpoints.
"""

from fastapi import APIRouter
from app.community.routers.posts import router as posts_router
from app.community.routers.comments import router as comments_router
from app.community.routers.likes import router as likes_router
from app.community.routers.polls import router as polls_router
from app.community.routers.reports import router as reports_router
from app.community.routers.moderation import router as moderation_router
from app.community.routers.dashboard import router as dashboard_router

# Unified community API router
community_router = APIRouter(prefix="/api/v1/community")

# Include posts router
community_router.include_router(posts_router, prefix="/posts", tags=["Community Posts"])

# Include comments router nested under posts
community_router.include_router(
    comments_router,
    prefix="/posts/{postId}/comments",
    tags=["Community Comments"]
)

# Include likes router nested under posts
community_router.include_router(
    likes_router,
    prefix="/posts/{postId}",
    tags=["Community Likes"]
)

# Include polls router nested under posts
community_router.include_router(
    polls_router,
    prefix="/posts/{postId}/poll",
    tags=["Community Polls"]
)

# Include reports router nested under posts
community_router.include_router(
    reports_router,
    prefix="/posts/{postId}",
    tags=["Community Reports"]
)

# Include moderation router
community_router.include_router(
    moderation_router,
    prefix="/moderation",
    tags=["Community Moderation"]
)

# Include dashboard router
community_router.include_router(
    dashboard_router,
    prefix="/moderation",
    tags=["Community Moderation Dashboard"]
)
