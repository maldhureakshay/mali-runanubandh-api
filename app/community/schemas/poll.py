"""
Poll schemas module.

Defines request and response validation structures for community polls.
"""

from typing import List
from pydantic import BaseModel, Field


class VoteRequest(BaseModel):
    """
    Request payload schema for casting a vote.
    """
    optionIds: List[str] = Field(..., min_items=1, description="List of option IDs voted for")


class PollOptionResult(BaseModel):
    """
    Represents voting metrics for a single poll option.
    """
    id: str = Field(..., description="Unique choice option ID")
    text: str = Field(..., description="Choice option text")
    votes: int = Field(..., description="Count of votes cast for this option")
    percentage: float = Field(..., description="Percentage of total votes this option received")


class PollResultsResponse(BaseModel):
    """
    API Response schema showing compiled results of a poll.
    """
    question: str = Field(..., description="The poll question")
    totalVotes: int = Field(..., description="Total aggregate votes cast across all options")
    options: List[PollOptionResult] = Field(..., description="Details and metrics for each option")
