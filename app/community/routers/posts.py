"""
Community Posts Router.

Defines REST API endpoints for Community Posts. Handles mapping to PostService,
response serialization, logging, and security role/ownership checks.
"""

import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query, Response, status

from app.community.enums import PostStatus, PostType, Visibility
from app.community.models.post import AuthorSnapshot
from app.community.schemas.post import PostCreate, PostResponse, PostUpdate
from app.community.services.post import PostService
from app.community.services.like import LikeService
from app.community.services.poll import PollService
from app.core.dependencies import (
    get_post_service,
    get_like_service,
    get_poll_service,
    get_current_user,
    get_current_user_optional,
    get_statistics_repository,
    AuthenticatedUser,
    ADMIN,
)
from app.community.repositories.statistics import StatisticsRepository
from app.community.routers.utils import (
    get_author_snapshot_from_firestore,
    enrich_posts_with_profile_snapshots
)
from app.core.exceptions import ForbiddenException
from app.core.responses import APIResponse, success_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=APIResponse[PostResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new community post",
    description="Registers a new community post. Only ADMIN users are allowed to create ANNOUNCEMENT posts.",
)
async def create_post(
    payload: PostCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
) -> Any:
    logger.info("REST Request - Create Post: type=%s, user=%s", payload.type, current_user.uid)
    
    # Announcement Rules: ANNOUNCEMENT posts can only be created by ADMIN users
    if payload.type == PostType.ANNOUNCEMENT:
        if ADMIN not in current_user.roles:
            logger.warning(
                "Authorization failure: User %s (Roles: %s) attempted to create ANNOUNCEMENT post.",
                current_user.uid,
                current_user.roles
            )
            raise ForbiddenException(message="Announcement posts can only be created by ADMIN users.")
            
    # Fetch AuthorSnapshot from Firebase users collection
    author = await get_author_snapshot_from_firestore(current_user)

    post = await post_service.create_post(
        content=payload.content,
        post_type=payload.type,
        author=author,
        metadata=payload.metadata,
        visibility=payload.visibility,
        status=payload.status
    )
    
    response_data = PostResponse.model_validate(post.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Post created successfully.",
        status_code=status.HTTP_201_CREATED
    )


@router.get(
    "/me/posts",
    response_model=APIResponse[List[PostResponse]],
    summary="Get current user's posts",
    description="Retrieves posts authored by the authenticated user. Optionally filter by status.",
)
async def get_my_posts(
    status_filter: Optional[PostStatus] = Query(None, alias="status", description="Filter by post status (e.g. DRAFT, APPROVED)"),
    limit: int = Query(20, ge=1, le=100, description="Max number of items to return"),
    cursor: Optional[str] = Query(None, description="Cursor for next page pagination"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service),
    like_service: LikeService = Depends(get_like_service),
    poll_service: PollService = Depends(get_poll_service)
) -> Any:
    logger.info("REST Request - Get My Posts: user=%s, status=%s", current_user.uid, status_filter)
    
    posts, next_cursor = await post_service.get_posts_by_author(
        user_id=current_user.uid,
        limit=limit,
        cursor=cursor,
        status=status_filter
    )
    
    liked_post_ids = set()
    user_votes = {}
    if current_user:
        post_ids = [str(p.id) for p in posts if p.id]
        liked_post_ids = await like_service.like_repo.get_liked_post_ids(post_ids, current_user.uid)
        user_votes = await poll_service.vote_repo.get_user_voted_options_batch(post_ids, current_user.uid)
        
    serialized_posts = []
    for post in posts:
        post_dict = post.model_dump(by_alias=True)
        post_dict["likedByCurrentUser"] = str(post.id) in liked_post_ids
        
        # Populate poll specific fields
        if post.type == PostType.POLL:
            post_id_str = str(post.id)
            has_voted = post_id_str in user_votes
            selected_opts = user_votes.get(post_id_str, [])
            post_dict["hasVoted"] = has_voted
            post_dict["selectedOptions"] = selected_opts
            
        serialized_posts.append(post_dict)
        
    enriched_posts = await enrich_posts_with_profile_snapshots(serialized_posts)
    
    final_responses = [
        PostResponse.model_validate(p).model_dump(mode="json") for p in enriched_posts
    ]
        
    meta_data = {}
    if next_cursor:
        meta_data["next_cursor"] = next_cursor

    return success_response(
        data=final_responses,
        message="My posts fetched successfully.",
        status_code=status.HTTP_200_OK,
        meta=meta_data if meta_data else None
    )


@router.get(
    "/",
    response_model=APIResponse[List[PostResponse]],
    summary="Get community feed",
    description="Retrieves a list of approved, active community posts using cursor-based pagination. This endpoint is public.",
)
async def get_feed(
    limit: int = Query(20, ge=1, le=100, description="Max number of items to return"),
    cursor: Optional[str] = Query(None, description="Cursor for next page pagination"),
    type: Optional[PostType] = Query(None, alias="type", description="Optional post type filter"),
    visibility: Visibility = Query(Visibility.PUBLIC, description="Target visibility audience filter"),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional),
    post_service: PostService = Depends(get_post_service),
    like_service: LikeService = Depends(get_like_service),
    poll_service: PollService = Depends(get_poll_service),
    stats_repo: StatisticsRepository = Depends(get_statistics_repository)
) -> Any:
    logger.info("REST Request - Get Feed: limit=%d, cursor=%s, type=%s, visibility=%s", limit, cursor, type, visibility)
    
    posts, next_cursor = await post_service.get_feed(
        visibility=visibility,
        limit=limit,
        cursor=cursor,
        post_type=type
    )
    
    liked_post_ids = set()
    user_votes = {}
    if current_user:
        post_ids = [str(p.id) for p in posts if p.id]
        liked_post_ids = await like_service.like_repo.get_liked_post_ids(post_ids, current_user.uid)
        user_votes = await poll_service.vote_repo.get_user_voted_options_batch(post_ids, current_user.uid)
        
    serialized_posts = []
    for post in posts:
        post_dict = post.model_dump(by_alias=True)
        post_dict["likedByCurrentUser"] = str(post.id) in liked_post_ids
        
        # Populate poll specific fields for authenticated requests
        if post.type == PostType.POLL:
            post_id_str = str(post.id)
            has_voted = post_id_str in user_votes
            selected_opts = user_votes.get(post_id_str, [])
            post_dict["hasVoted"] = has_voted
            post_dict["selectedOptions"] = selected_opts
            
        serialized_posts.append(post_dict)
        
    enriched_posts = await enrich_posts_with_profile_snapshots(serialized_posts)
    
    final_responses = [
        PostResponse.model_validate(p).model_dump(mode="json") for p in enriched_posts
    ]
        
    stats = await stats_repo.get_statistics()
    
    meta = {
        "statistics": {
            "members": stats.members if stats else "0",
            "activeProfiles": stats.activeProfiles if stats else "0",
            "doctors": stats.doctors if stats else "0",
            "engineers": stats.engineers if stats else "0",
            "new": stats.new if stats else "0",
            "verified": stats.verified if stats else "0",
            "subcastes": ["Gase", "Jire", "Phool", "Kase", "Bhaure", "Marar", "Lonari", "Saini", "Kosare", "Halade", "Savata", "Kach Lingayat", "Kadu", "Bawane", "Adhyaprabhu", "Vanmali"]
        }
    }
        
    return success_response(
        data=final_responses,
        message="Feed fetched successfully.",
        status_code=status.HTTP_200_OK,
        meta=meta
    )


@router.get(
    "/{postId}",
    response_model=APIResponse[PostResponse],
    summary="Get post details",
    description="Fetches a specific post by ID and atomically increments the viewsCount statistic. This endpoint is public.",
)
async def get_post_details(
    postId: str,
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional),
    post_service: PostService = Depends(get_post_service),
    like_service: LikeService = Depends(get_like_service),
    poll_service: PollService = Depends(get_poll_service)
) -> Any:
    logger.info("REST Request - Get Post Details: postId=%s", postId)
    
    post = await post_service.get_post(postId)
    
    # Increment view count atomically
    updated_post = await post_service.post_repo.increment_views(postId)
    
    liked = False
    has_voted = False
    selected_opts = []
    
    if current_user:
        liked = await like_service.has_user_liked(postId, current_user.uid)
        if updated_post.type == PostType.POLL:
            votes = await poll_service.vote_repo.get_user_votes(postId, current_user.uid)
            has_voted = len(votes) > 0
            selected_opts = [v.optionId for v in votes]
            
    post_dict = updated_post.model_dump(by_alias=True)
    post_dict["likedByCurrentUser"] = liked
    post_dict["hasVoted"] = has_voted
    post_dict["selectedOptions"] = selected_opts
    
    enriched_posts = await enrich_posts_with_profile_snapshots([post_dict])
    post_dict = enriched_posts[0]
    
    response_data = PostResponse.model_validate(post_dict)
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Post details fetched successfully."
    )


@router.put(
    "/{postId}",
    response_model=APIResponse[PostResponse],
    summary="Update a post",
    description="Updates content, metadata, or visibility on an existing post. Only the author or an ADMIN may update.",
)
async def update_post(
    postId: str,
    payload: PostUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
) -> Any:
    logger.info("REST Request - Update Post: postId=%s, user=%s", postId, current_user.uid)
    
    # 1. Fetch current post details
    post = await post_service.get_post(postId)
    
    # 2. Enforce ownership: users may only update their own posts, unless ADMIN
    if post.author.userId != current_user.uid and ADMIN not in current_user.roles:
        logger.warning(
            "Authorization failure: User %s (Roles: %s) requested update on post %s owned by %s.",
            current_user.uid,
            current_user.roles,
            postId,
            post.author.userId
        )
        raise ForbiddenException(message="You do not have permission to update this post.")

    updated_post = await post_service.update_post(
        post_id=postId,
        content=payload.content,
        metadata=payload.metadata,
        visibility=payload.visibility,
        status=payload.status
    )
    
    response_data = PostResponse.model_validate(updated_post.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Post updated successfully."
    )


@router.delete(
    "/{postId}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Soft delete a post",
    description="Soft-deletes a post by switching moderation.status to DELETED. Only the author or an ADMIN may delete.",
)
async def delete_post(
    postId: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
) -> Any:
    logger.info("REST Request - Delete Post: postId=%s, user=%s", postId, current_user.uid)
    
    # 1. Fetch current post details
    post = await post_service.get_post(postId)
    
    # 2. Enforce ownership: users may only delete their own posts, unless ADMIN
    if post.author.userId != current_user.uid and ADMIN not in current_user.roles:
        logger.warning(
            "Authorization failure: User %s (Roles: %s) requested deletion on post %s owned by %s.",
            current_user.uid,
            current_user.roles,
            postId,
            post.author.userId
        )
        raise ForbiddenException(message="You do not have permission to delete this post.")

    await post_service.delete_post(postId)
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post(
    "/{postId}/submit",
    response_model=APIResponse[PostResponse],
    summary="Submit a post for moderation",
    description="Submits a draft post for review. Only the owner can submit. Changes status to PENDING_REVIEW.",
)
async def submit_post(
    postId: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    post_service: PostService = Depends(get_post_service)
) -> Any:
    logger.info("REST Request - Submit Post: postId=%s, user=%s", postId, current_user.uid)
    
    updated_post = await post_service.submit_post(
        post_id=postId,
        user_id=current_user.uid
    )
    
    response_data = PostResponse.model_validate(updated_post.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Post submitted for review successfully.",
        status_code=status.HTTP_200_OK
    )
