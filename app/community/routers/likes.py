"""
Community Likes Router.

Defines REST API endpoints for liking and unliking posts, and fetching like status.
"""

import logging
from typing import Any, List
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from app.community.services.like import LikeService
from app.community.models.post import AuthorSnapshot
from app.core.dependencies import get_like_service, get_current_user, AuthenticatedUser
from app.core.responses import APIResponse, success_response

logger = logging.getLogger(__name__)

# Router will be included with a prefix in the main community router
router = APIRouter()


class LikeStatusResponse(BaseModel):
    """
    Response schema returning the liking status of the current user.
    """
    liked: bool = Field(..., description="Whether the authenticated user has liked this post")


@router.post(
    "/like",
    response_model=APIResponse[dict],
    status_code=status.HTTP_201_CREATED,
    summary="Like a post",
    description="Registers a like reaction on the specified post. Returns 409 Conflict if already liked.",
)
async def like_post(
    postId: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    like_service: LikeService = Depends(get_like_service)
) -> Any:
    logger.info("REST Request - Like Post: postId=%s, user=%s", postId, current_user.uid)
    
    await like_service.like_post(post_id=postId, user_id=current_user.uid)
    
    return success_response(
        data={},
        message="Post liked successfully.",
        status_code=status.HTTP_201_CREATED
    )


@router.delete(
    "/like",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Unlike a post",
    description="Removes a like reaction from the specified post. This operation is idempotent.",
)
async def unlike_post(
    postId: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    like_service: LikeService = Depends(get_like_service)
) -> Any:
    logger.info("REST Request - Unlike Post: postId=%s, user=%s", postId, current_user.uid)
    
    await like_service.unlike_post(post_id=postId, user_id=current_user.uid)
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/like/status",
    response_model=APIResponse[LikeStatusResponse],
    summary="Get post like status",
    description="Returns whether the authenticated user has liked the target post.",
)
async def get_like_status(
    postId: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    like_service: LikeService = Depends(get_like_service)
) -> Any:
    logger.info("REST Request - Get Like Status: postId=%s, user=%s", postId, current_user.uid)
    
    liked = await like_service.has_user_liked(post_id=postId, user_id=current_user.uid)
    
    return success_response(
        data=LikeStatusResponse(liked=liked),
        message="Like status retrieved successfully."
    )


@router.get(
    "/likes",
    response_model=APIResponse[List[AuthorSnapshot]],
    summary="Get users who liked a post",
    description="Retrieves snapshots of the users who liked the target post.",
)
async def get_post_likers(
    postId: str,
    like_service: LikeService = Depends(get_like_service)
) -> Any:
    logger.info("REST Request - Get Post Likers: postId=%s", postId)
    
    likers = await like_service.get_post_likers(post_id=postId)
    
    return success_response(
        data=likers,
        message="Post likers retrieved successfully."
    )
