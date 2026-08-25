"""
Repositories subpackage for the Community Service module.

Exposes repositories for Posts, Comments, Likes, and Reports,
along with generic BaseRepository and custom exceptions.
"""

from app.community.repositories.base import BaseRepository
from app.community.repositories.post import PostRepository
from app.community.repositories.comment import CommentRepository
from app.community.repositories.like import LikeRepository
from app.community.repositories.report import ReportRepository
from app.community.repositories.exceptions import (
    RepositoryException,
    DocumentNotFoundException,
    InvalidCursorException,
)

__all__ = [
    "BaseRepository",
    "PostRepository",
    "CommentRepository",
    "LikeRepository",
    "ReportRepository",
    "RepositoryException",
    "DocumentNotFoundException",
    "InvalidCursorException",
]
