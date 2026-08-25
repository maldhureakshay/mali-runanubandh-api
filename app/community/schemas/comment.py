"""
Comment Schemas module.

Defines Pydantic request and response schemas for validating comments API requests.
"""

from datetime import datetime
from pydantic import BaseModel, Field

from app.community.models.post import AuthorSnapshot


class CommentCreate(BaseModel):
    """
    Request payload schema to create/edit a comment.
    """
    comment: str = Field(..., min_length=1, max_length=1000, description="Comment text body content")


class CommentResponse(BaseModel):
    """
    API Response schema returning comment details.
    """
    id: str = Field(..., alias="_id", description="MongoDB comment ID")
    author: AuthorSnapshot = Field(..., description="Author details snapshot")
    comment: str = Field(..., description="Text content body")
    edited: bool = Field(False, description="Flag indicating if comment was edited")
    createdAt: datetime = Field(..., description="Comment creation UTC timestamp")

    model_config = {
        "populate_by_name": True
    }
