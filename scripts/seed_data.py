import asyncio
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONGO_URI = "mongodb://localhost:27017/matrimony"
MONGO_DB_NAME = "matrimony"
MONGO_COLLECTION_NAME = "profiles"

# Mock profiles with stable, static UUIDs around Maharashtra and one far away in Kolkata.
# Having static IDs ensures idempotency and clean overrides on subsequent runs.
MOCK_PROFILES = [
    {
        "_id": "4a62dc3a-3d51-43eb-9295-2a310a143e5a", # Rutuja (Amravati region - Paratwada)
        "type": "First Marriage",
        "payment_status": "complete",
        "original_id": "597",
        "full_name": "Rutuja Rajkumar Maldhure",
        "first_name": "Rutuja",
        "last_name": "Maldhure",
        "gender": "female",
        "active": True,
        "is_verified": True,
        "birth_date": "1996-08-04T00:00:00.000",
        "education": "Engineer",
        "job": "Senior Software Engineer at WNS",
        "job_location": "Pune",
        "fathers_address": "Kavitha road, Kandali, Paratwada",
        "fathers_address_latitude": 21.2969484,
        "fathers_address_longitude": 77.5233886,
        "_geohash": "tez1hhfz9",
        "_geoloc": {"lng": 77.5233886, "lat": 21.2969484},
        "created": datetime.fromisoformat("2026-01-01T18:30:00.032"),
        "modified": datetime.fromisoformat("2026-05-30T09:28:20.392"),
        "is_featured": False
    },
    {
        "_id": "b3e0d84a-9b14-41d6-b184-e91b2c45187e", # Snehal (Pune center)
        "type": "First Marriage",
        "payment_status": "complete",
        "full_name": "Snehal Dinkar Patil",
        "first_name": "Snehal",
        "last_name": "Patil",
        "gender": "female",
        "active": True,
        "is_verified": True,
        "birth_date": "1997-12-14T00:00:00.000",
        "education": "BTech IT",
        "job": "QA Engineer at TCS",
        "job_location": "Pune",
        "fathers_address": "Shivajinagar, Pune Center",
        "fathers_address_latitude": 18.5204,
        "fathers_address_longitude": 73.8567,
        "_geohash": "tejy41q1u",
        "_geoloc": {"lng": 73.8567, "lat": 18.5204},
        "created": datetime.now(),
        "is_featured": True
    },
    {
        "_id": "c1f7a83d-3d44-4b5d-9c3f-42a129dcb91e", # Rajesh (Pune Suburb)
        "type": "First Marriage",
        "payment_status": "complete",
        "full_name": "Rajesh Vasant Kulkarni",
        "first_name": "Rajesh",
        "last_name": "Kulkarni",
        "gender": "male",
        "active": True,
        "is_verified": True,
        "birth_date": "1994-04-10T00:00:00.000",
        "education": "ME Electronics",
        "job": "Hardware Engineer at Intel",
        "job_location": "Pune",
        "fathers_address": "Hadapsar, Pune",
        "fathers_address_latitude": 18.5089,
        "fathers_address_longitude": 73.9259,
        "_geohash": "tejy4w3c4",
        "_geoloc": {"lng": 73.9259, "lat": 18.5089},
        "created": datetime.now(),
        "is_featured": False
    },
    {
        "_id": "d7a31b2c-619f-4318-874b-e8543fbe0a1d", # Amit (Amravati center)
        "type": "First Marriage",
        "payment_status": "complete",
        "full_name": "Amit Prakash Maldhure",
        "first_name": "Amit",
        "last_name": "Maldhure",
        "gender": "male",
        "active": True,
        "is_verified": True,
        "birth_date": "1995-02-28T00:00:00.000",
        "education": "MBA Marketing",
        "job": "Sales Manager at HDFC Bank",
        "job_location": "Amravati",
        "fathers_address": "Sai Nagar, Amravati Center",
        "fathers_address_latitude": 20.9320,
        "fathers_address_longitude": 77.7523,
        "_geohash": "tez17ey22",
        "_geoloc": {"lng": 77.7523, "lat": 20.9320},
        "created": datetime.now(),
        "is_featured": False
    },
    {
        "_id": "e2d4cf67-75e1-45da-9c88-7241fb7a641e", # Priya (Akola - near Amravati)
        "type": "First Marriage",
        "payment_status": "complete",
        "full_name": "Priya Ramesh Deshmukh",
        "first_name": "Priya",
        "last_name": "Deshmukh",
        "gender": "female",
        "active": True,
        "is_verified": False, # Unverified to test filters
        "birth_date": "1998-05-22T00:00:00.000",
        "education": "BCom",
        "job": "Accountant",
        "job_location": "Akola",
        "fathers_address": "Geeta Nagar, Akola",
        "fathers_address_latitude": 20.7002,
        "fathers_address_longitude": 77.0082,
        "_geohash": "teyckge4e",
        "_geoloc": {"lng": 77.0082, "lat": 20.7002},
        "created": datetime.now(),
        "is_featured": False
    },
    {
        "_id": "f5e6b7d8-21da-45e3-82a1-fa4cfdb1920d", # Rahul (Mumbai center)
        "type": "First Marriage",
        "payment_status": "complete",
        "full_name": "Rahul Kumar Sharma",
        "first_name": "Rahul",
        "last_name": "Sharma",
        "gender": "male",
        "active": True,
        "is_verified": True,
        "birth_date": "1993-10-18T00:00:00.000",
        "education": "BTech CS",
        "job": "Tech Lead at Jio",
        "job_location": "Mumbai",
        "fathers_address": "Andheri West, Mumbai",
        "fathers_address_latitude": 19.0760,
        "fathers_address_longitude": 72.8777,
        "_geohash": "te7udg0w0",
        "_geoloc": {"lng": 72.8777, "lat": 19.0760},
        "created": datetime.now(),
        "is_featured": False
    },
    {
        "_id": "a9d8c7b6-14ea-4efd-b9cf-da3c2df1a48c", # Neha (Kolkata - far away)
        "type": "First Marriage",
        "payment_status": "complete",
        "full_name": "Neha Anup Shinde",
        "first_name": "Neha",
        "last_name": "Shinde",
        "gender": "female",
        "active": True,
        "is_verified": True,
        "birth_date": "1996-07-04T00:00:00.000",
        "education": "MTech",
        "job": "Research Scientist",
        "job_location": "Kolkata",
        "fathers_address": "Salt Lake, Kolkata Center",
        "fathers_address_latitude": 22.5726,
        "fathers_address_longitude": 88.3639,
        "_geohash": "tup96geee",
        "_geoloc": {"lng": 88.3639, "lat": 22.5726},
        "created": datetime.now(),
        "is_featured": False
    },
    {
        "_id": "3c8d9e7a-d4fa-4b1a-8cde-e91b2c45187e", # Inactive Profile
        "type": "First Marriage",
        "payment_status": "pending",
        "full_name": "Inactive Profile",
        "first_name": "Inactive",
        "last_name": "Profile",
        "gender": "male",
        "active": False, # Inactive to test status filters
        "is_verified": True,
        "fathers_address_latitude": 18.5204,
        "fathers_address_longitude": 73.8567,
        "_geoloc": {"lng": 73.8567, "lat": 18.5204},
        "created": datetime.now(),
        "is_featured": False
    }
]

async def seed():
    logger.info(f"Connecting to MongoDB at {MONGO_URI}...")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    collection = db[MONGO_COLLECTION_NAME]
    
    # Clean the entire profile collection to eliminate any duplicates from dynamic UUID runs
    logger.info("Wiping existing profile collection to start with a fresh clean state...")
    delete_result = await collection.delete_many({})
    logger.info(f"Cleared {delete_result.deleted_count} stale documents from collection.")
    
    # Insert mock records
    logger.info(f"Seeding {len(MOCK_PROFILES)} realistic profiles...")
    insert_result = await collection.insert_many(MOCK_PROFILES)
    logger.info(f"Successfully seeded {len(insert_result.inserted_ids)} documents.")
    
    # Make sure spatial index is created
    logger.info("Ensuring 2dsphere spatial index on '_geoloc'...")
    index_name = await collection.create_index([("_geoloc", "2dsphere")], name="geoloc_2dsphere_idx")
    logger.info(f"Index check complete: {index_name}")
    
    client.close()
    logger.info("Database seeding finished successfully!")

if __name__ == "__main__":
    asyncio.run(seed())
