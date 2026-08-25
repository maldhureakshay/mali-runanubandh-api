"""
Notification validation schemas.

Defines Pydantic schemas for notifications request and response payloads.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """
    API Response schema for a notification document.
    """
    id: str = Field(..., alias="_id", description="The notification ID")
    recipientUserId: str = Field(..., description="Recipient user ID")
    actorUserId: Optional[str] = Field(None, description="Triggering actor user ID")
    type: str = Field(..., description="Notification type category")
    title: str = Field(..., description="Notification header title")
    message: str = Field(..., description="Notification message body")
    referenceType: Optional[str] = Field(None, description="Referenced collection category")
    referenceId: Optional[str] = Field(None, description="Referenced database entity ID")
    read: bool = Field(..., description="Read status flag")
    readAt: Optional[datetime] = Field(None, description="UTC read timestamp")
    createdAt: datetime = Field(..., description="UTC creation timestamp")

    model_config = {
        "populate_by_name": True
    }


class UnreadCountResponse(BaseModel):
    """
    API Response schema returning the unread notification count.
    """
    unreadCount: int = Field(..., description="Count of unread notifications for the user")
