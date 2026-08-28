"""
PollVote domain model.

Defines the structure of a user's vote on a community poll.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PollVote(BaseModel):
    """
    Domain model representing a vote cast in a community poll.
    """
    model_config = ConfigDict(
        populate_by_name=True
    )

    @model_validator(mode="before")
    @classmethod
    def convert_object_id(cls, data: Any) -> Any:
        """Coerce MongoDB ObjectId into a string."""
        if isinstance(data, dict):
            if "_id" in data and not isinstance(data["_id"], str):
                data["_id"] = str(data["_id"])
        return data

    id: Optional[str] = Field(None, alias="_id", description="MongoDB ObjectId hex string")
    postId: str = Field(..., description="Target post ID representing the poll")
    optionId: str = Field(..., description="The option identifier voted for")
    userId: str = Field(..., description="The user ID who cast the vote")
    allowMultipleSelection: bool = Field(False, description="Denotes if poll allowed multi-select, used for partial unique indexes")
    createdAt: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp when the vote was cast")
