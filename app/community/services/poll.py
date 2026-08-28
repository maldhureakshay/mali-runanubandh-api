"""
Poll Service module.

Implements business logic for voting in polls and fetching poll results.
"""

from datetime import datetime, timezone
import logging
from typing import Any, List, Dict

from pymongo.errors import DuplicateKeyError

from app.community.models.poll_vote import PollVote
from app.community.enums import PostStatus, PostType
from app.community.repositories.post import PostRepository
from app.community.repositories.vote import VoteRepository
from app.community.repositories.exceptions import DocumentNotFoundException
from app.community.services.exceptions import (
    DuplicateVoteException,
    PollExpiredException,
    PostDeletedException,
    PostNotFoundException,
    ValidationException,
)

from app.events.event_types import EventType

logger = logging.getLogger(__name__)


class PollService:
    """
    Orchestrates business operations for casting votes and compiling poll results.
    """

    def __init__(self, vote_repo: VoteRepository, post_repo: PostRepository, event_publisher: Any = None) -> None:
        """
        Injects repositories and optional EventPublisher.
        """
        self.vote_repo = vote_repo
        self.post_repo = post_repo
        self.event_publisher = event_publisher

    async def vote_in_poll(
        self,
        post_id: str,
        user_id: str,
        option_ids: List[str],
        session: Any = None
    ) -> bool:
        """
        Cast a vote on a community poll post.
        """
        # 1. Fetch post and verify existence
        try:
            post = await self.post_repo.get_post(post_id)
        except DocumentNotFoundException:
            raise PostNotFoundException("Poll post does not exist.")

        # 2. Enforce post is of type POLL, is APPROVED and not DELETED
        if post.type != PostType.POLL:
            raise ValidationException("Target post is not a poll.")
            
        if post.moderation.status == PostStatus.DELETED:
            raise PostDeletedException("Cannot vote on a deleted poll.")
            
        if post.moderation.status != PostStatus.APPROVED:
            raise ValidationException("Cannot vote on a poll that is not approved.")

        # 3. Check expiry
        poll_meta = post.metadata
        if not poll_meta:
            raise ValidationException("Poll metadata is missing.")

        current_time = datetime.now(timezone.utc)
        if poll_meta.expiresAt and poll_meta.expiresAt.replace(tzinfo=timezone.utc) < current_time:
            logger.warning("Expired poll vote attempt: User %s on poll %s.", user_id, post_id)
            raise PollExpiredException()

        # 4. Check option IDs validity
        valid_option_ids = {opt.id for opt in poll_meta.options}
        if not all(opt_id in valid_option_ids for opt_id in option_ids):
            raise ValidationException("One or more selected options are invalid.")

        # 5. Enforce single/multiple selection count rules
        allow_multiple = poll_meta.allowMultipleSelection
        if not allow_multiple:
            if len(option_ids) != 1:
                raise ValidationException("Exactly one option must be selected for this poll.")
        else:
            if len(option_ids) < 1:
                raise ValidationException("At least one option must be selected.")

        # 6. Check for duplicate vote (Retract/change vote support)
        already_voted = await self.vote_repo.has_user_voted(post_id, user_id)
        if already_voted:
            existing_votes = await self.vote_repo.get_user_votes(post_id, user_id)
            existing_option_ids = [v.optionId for v in existing_votes]
            
            # If user votes for the exact same options, raise DuplicateVoteException
            if set(existing_option_ids) == set(option_ids):
                logger.warning("Duplicate vote: User %s already voted in poll %s for option %s.", user_id, post_id, option_ids)
                raise DuplicateVoteException()
                
            # Otherwise, delete existing votes and decrement option counts
            await self.vote_repo.delete_user_votes(post_id, user_id)
            await self.post_repo.decrement_poll_option_votes(post_id, existing_option_ids)

        # 7. Save vote documents
        votes = [
            PollVote(
                postId=post_id,
                optionId=opt_id,
                userId=user_id,
                allowMultipleSelection=allow_multiple,
                createdAt=datetime.now(timezone.utc)
            )
            for opt_id in option_ids
        ]

        try:
            for vote in votes:
                await self.vote_repo.create_vote(vote)
        except DuplicateKeyError:
            logger.warning("Duplicate vote: User %s duplicate vote DB constraint in poll %s.", user_id, post_id)
            raise DuplicateVoteException()

        # 8. Atomically update post option counters
        await self.post_repo.increment_poll_option_votes(post_id, option_ids)

        logger.info("Vote submitted: User %s voted for options %s in poll %s.", user_id, option_ids, post_id)
        if self.event_publisher:
            await self.event_publisher.publish(
                EventType.POLL_VOTED,
                {
                    "postId": post_id,
                    "userId": user_id,
                    "optionIds": option_ids
                }
            )
        return True

    async def get_poll_results(self, post_id: str) -> Dict[str, Any]:
        """
        Compile poll question, options, vote counts, total votes, and percentages.
        """
        try:
            post = await self.post_repo.get_post(post_id)
        except DocumentNotFoundException:
            raise PostNotFoundException("Poll post does not exist.")

        if post.type != PostType.POLL:
            raise ValidationException("Target post is not a poll.")

        poll_meta = post.metadata
        if not poll_meta:
            raise ValidationException("Poll metadata is missing.")

        # Compute total votes
        total_votes = sum(opt.votesCount for opt in poll_meta.options)

        options_results = []
        for opt in poll_meta.options:
            percentage = round((opt.votesCount / total_votes) * 100, 2) if total_votes > 0 else 0.0
            options_results.append({
                "id": opt.id,
                "text": opt.text,
                "votes": opt.votesCount,
                "percentage": percentage
            })

        return {
            "question": poll_meta.question,
            "totalVotes": total_votes,
            "options": options_results
        }
