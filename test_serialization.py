import asyncio
from datetime import datetime, timezone
import sys
sys.path.append("/Users/akshaykumarmaldhure/work/matrimony-api")
from app.community.models.post import Post, Content, Moderation, AuthorSnapshot, VisibilitySettings
from app.community.schemas.moderation import PendingPostSummaryResponse
from app.community.enums import PostType, PostStatus, Visibility
from pydantic import ValidationError

def test_serialization():
    post = Post(
        type=PostType.POST,
        author=AuthorSnapshot(userId="123", profileId="456", fullName="Test Author", profileImage=None),
        content=Content(title="Test Title", body="Test Body", images=[]),
        moderation=Moderation(status=PostStatus.PENDING_REVIEW),
        visibility=VisibilitySettings(visibility=Visibility.PUBLIC),
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc)
    )
    
    # Simulate repository returning domain model
    post_dict = post.model_dump(by_alias=True)
    
    # Simulate router serializing to response model
    response = PendingPostSummaryResponse.model_validate(post_dict)
    print(response.model_dump_json(by_alias=True, indent=2))

if __name__ == "__main__":
    test_serialization()
