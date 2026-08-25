"""
Constants module.

Stores shared, immutable variables and configurations (e.g. database collection names).
"""

# Collection Names
POSTS_COLLECTION = "community_posts"
COMMENTS_COLLECTION = "community_comments"
LIKES_COLLECTION = "community_likes"
REPORTS_COLLECTION = "community_reports"
SUCCESS_STORIES_COLLECTION = "success_stories"

# System limits
MAX_POST_CONTENT_LENGTH = 5000
MAX_COMMENT_CONTENT_LENGTH = 1000
PAGINATION_DEFAULT_LIMIT = 20
PAGINATION_MAX_LIMIT = 100
