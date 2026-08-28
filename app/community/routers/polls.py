"""
Community Polls Router.

Defines REST API endpoints for voting in polls and fetching poll results.
"""

import logging
from typing import Any
from fastapi import APIRouter, Depends, status

from app.community.schemas.poll import VoteRequest, PollResultsResponse
from app.community.services.poll import PollService
from app.core.dependencies import get_poll_service, get_current_user, AuthenticatedUser
from app.core.responses import APIResponse, success_response

logger = logging.getLogger(__name__)

# Router will be included with a nested prefix in the main community router
router = APIRouter()


@router.post(
    "/vote",
    response_model=APIResponse[dict],
    status_code=status.HTTP_201_CREATED,
    summary="Vote in a poll",
    description="Casts a vote on one or more options in a poll post. Returns 409 Conflict if user has already voted.",
)
async def vote_in_poll(
    postId: str,
    payload: VoteRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    poll_service: PollService = Depends(get_poll_service)
) -> Any:
    logger.info("REST Request - Vote In Poll: postId=%s, user=%s, options=%s", postId, current_user.uid, payload.optionIds)
    
    await poll_service.vote_in_poll(
        post_id=postId,
        user_id=current_user.uid,
        option_ids=payload.optionIds
    )
    
    return success_response(
        data={},
        message="Vote submitted successfully.",
        status_code=status.HTTP_201_CREATED
    )


@router.get(
    "/results",
    response_model=APIResponse[PollResultsResponse],
    summary="Get poll results",
    description="Compiles and returns the current question, options, aggregate votes, and percentage distribution.",
)
async def get_poll_results(
    postId: str,
    poll_service: PollService = Depends(get_poll_service)
) -> Any:
    logger.info("REST Request - Get Poll Results: postId=%s", postId)
    
    results = await poll_service.get_poll_results(post_id=postId)
    
    return success_response(
        data=PollResultsResponse.model_validate(results),
        message="Poll results compiled successfully."
    )
