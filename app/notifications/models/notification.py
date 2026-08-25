"""
Notification domain model.

Defines the structure of a notification document stored in MongoDB.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Notification(BaseModel):
    """
    Domain model representing a user notification.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
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
    recipientUserId: str = Field(..., description="The user ID of the recipient who receives the notification")
    actorUserId: Optional[str] = Field(None, description="The user ID of the actor performing the triggering action")
    type: str = Field(..., description="Type of the notification (e.g., POST_APPROVED, COMMENT_ADDED)")
    title: str = Field(..., description="Short title header of the notification")
    message: str = Field(..., description="Detail message content body")
    referenceType: Optional[str] = Field(None, description="Model type referenced (e.g., POST, COMMENT)")
    referenceId: Optional[str] = Field(None, description="Database ID of the referenced model")
    read: bool = Field(False, description="Whether the notification has been marked read")
    readAt: Optional[datetime] = Field(None, description="UTC timestamp when the notification was read")
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp when the notification was created")
