"""
Community Comments Router.

Defines REST API endpoints for Comments. Handles mapping to CommentService,
response serialization, logging, and security validations.
"""

import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query, Response, status

from app.community.models.post import AuthorSnapshot
from app.community.schemas.comment import CommentCreate, CommentResponse
from app.community.services.comment import CommentService
from app.core.dependencies import get_comment_service, get_current_user, AuthenticatedUser, ADMIN
from app.community.routers.utils import get_author_snapshot_from_firestore
from app.core.responses import APIResponse, success_response

logger = logging.getLogger(__name__)

# Router will be included in the main community router with a nested prefix
router = APIRouter()


@router.post(
    "",
    response_model=APIResponse[CommentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a comment on a post",
    description="Adds a new comment text to the specified post, updating comment statistics atomically. Requires authentication.",
)
async def create_comment(
    postId: str,
    payload: CommentCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    comment_service: CommentService = Depends(get_comment_service)
) -> Any:
    logger.info("REST Request - Create Comment: postId=%s, user=%s", postId, current_user.uid)
    
    # Fetch AuthorSnapshot from Firebase users collection
    author = await get_author_snapshot_from_firestore(current_user)

    comment = await comment_service.create_comment(
        post_id=postId,
        author=author,
        comment_text=payload.comment
    )
    
    response_data = CommentResponse.model_validate(comment.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Comment added successfully.",
        status_code=status.HTTP_201_CREATED
    )


@router.get(
    "",
    response_model=APIResponse[List[CommentResponse]],
    summary="Get comments for a post",
    description="Retrieves a list of active comments for a specific post using cursor-based pagination, sorted by oldest first.",
)
async def get_comments(
    postId: str,
    limit: int = Query(20, ge=1, le=100, description="Max number of items to return"),
    cursor: Optional[str] = Query(None, description="Cursor for next page pagination"),
    comment_service: CommentService = Depends(get_comment_service)
) -> Any:
    logger.info("REST Request - Get Comments: postId=%s, limit=%d, cursor=%s", postId, limit, cursor)
    
    comments, next_cursor = await comment_service.get_comments(
        post_id=postId,
        limit=limit,
        cursor=cursor
    )
    
    serialized_comments = [
        CommentResponse.model_validate(c.model_dump(by_alias=True)).model_dump(mode="json")
        for c in comments
    ]
    
    return success_response(
        data=serialized_comments,
        message="Comments fetched successfully.",
        status_code=status.HTTP_200_OK
    )


@router.put(
    "/{commentId}",
    response_model=APIResponse[CommentResponse],
    summary="Update a comment",
    description="Allows editing of the comment text. Only the owner of the comment can update it.",
)
async def update_comment(
    postId: str,
    commentId: str,
    payload: CommentCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    comment_service: CommentService = Depends(get_comment_service)
) -> Any:
    logger.info("REST Request - Update Comment: postId=%s, commentId=%s, user=%s", postId, commentId, current_user.uid)
    
    updated = await comment_service.update_comment(
        comment_id=commentId,
        current_user_uid=current_user.uid,
        new_text=payload.comment
    )
    
    response_data = CommentResponse.model_validate(updated.model_dump(by_alias=True))
    
    return success_response(
        data=response_data.model_dump(mode="json"),
        message="Comment updated successfully."
    )


@router.delete(
    "/{commentId}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Delete a comment",
    description="Soft-deletes the comment, updating comment statistics atomically. Only the owner or an ADMIN can delete.",
)
async def delete_comment(
    postId: str,
    commentId: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    comment_service: CommentService = Depends(get_comment_service)
) -> Any:
    logger.info("REST Request - Delete Comment: postId=%s, commentId=%s, user=%s", postId, commentId, current_user.uid)
    
    is_admin = ADMIN in current_user.roles
    await comment_service.delete_comment(
        comment_id=commentId,
        current_user_uid=current_user.uid,
        is_admin=is_admin
    )
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)
