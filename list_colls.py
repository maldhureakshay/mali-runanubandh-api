import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["matrimony"]
    colls = await db.list_collection_names()
    print("Collections in matrimony db:", colls)

if __name__ == "__main__":
    asyncio.run(main())
