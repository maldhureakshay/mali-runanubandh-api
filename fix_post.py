import asyncio
import os
from bson import ObjectId
from pymongo.errors import PyMongoError
import sys

sys.path.append("/Users/akshaykumarmaldhure/work/matrimony-api")
from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def update_post_status():
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]
    
    post_id = "6a68d9da307e639665fee0db"
    print(f"Updating post {post_id}...")
    
    result = await db.posts.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {"moderation.status": "PENDING_REVIEW"}}
    )
    
    if result.matched_count:
        print("Successfully updated post status to PENDING_REVIEW.")
    else:
        print("Post not found.")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(update_post_status())
