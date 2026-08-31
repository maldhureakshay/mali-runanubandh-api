import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["matrimony"]
    profile = await db.profiles.find_one()
    print("Sample profile keys:", list(profile.keys()) if profile else "No profile")
    if profile:
        print("active:", profile.get("active"))
        print("is_verified:", profile.get("is_verified"))
        print("verified:", profile.get("verified"))

if __name__ == "__main__":
    asyncio.run(main())
