import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def run():
    client = AsyncIOMotorClient('mongodb://localhost:27017/')
    db = client['matrimony']
    posts = db['posts']
    pinned_posts = await posts.find({'metadata.priority': 'HIGH'}).to_list(None)
    for p in pinned_posts:
        print(f"Post {p['_id']}: isPinned={p.get('isPinned')}, priority={p.get('metadata', {}).get('priority')}")
    
    # Fix existing pinned posts
    result = await posts.update_many(
        {'type': 'ANNOUNCEMENT', 'metadata.priority': 'HIGH'},
        {'$set': {'isPinned': True}}
    )
    print(f'Updated {result.modified_count} existing pinned posts.')
    
    # Fix missing for others
    result2 = await posts.update_many(
        {'isPinned': {'$exists': False}},
        {'$set': {'isPinned': False}}
    )
    print(f'Updated {result2.modified_count} other posts to have isPinned=False.')

asyncio.run(run())
