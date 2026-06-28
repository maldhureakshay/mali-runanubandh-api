import logging
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from database import db_manager
from models.profile import ProfileBase, ProfileWithDistance
from models.common import PaginatedResponse

logger = logging.getLogger(__name__)

class ProfileService:
    """
    ProfileService handles the business logic and MongoDB queries
    for geo-location matching, filtering, and pagination.
    """
    
    @staticmethod
    def validate_coordinates(lat: float, lng: float) -> Tuple[bool, Optional[str]]:
        """
        Validates that latitude and longitude parameters fall within physical limits.
        """
        if not (-90.0 <= lat <= 90.0):
            return False, "Latitude must be between -90.0 and 90.0 degrees."
        if not (-180.0 <= lng <= 180.0):
            return False, "Longitude must be between -180.0 and 180.0 degrees."
        return True, None

    async def find_nearby_profiles(
        self,
        lat: float,
        lng: float,
        page: int = 1,
        limit: int = 10,
        max_distance_km: Optional[float] = None,
        gender: Optional[str] = None,
        is_verified: Optional[bool] = None,
        active_only: bool = True
    ) -> PaginatedResponse[ProfileWithDistance]:
        """
        Executes an aggregation query using MongoDB's $geoNear pipeline to find
        the nearest profiles to a given point. Integrates facet-based pagination
        to return total matched records and paginated data in a single DB request.
        """
        # 1. Validate coordinates
        is_valid, error_msg = self.validate_coordinates(lat, lng)
        if not is_valid:
            raise ValueError(error_msg)

        collection = db_manager.get_collection()
        skip = (page - 1) * limit

        # 2. Build filters for the geoNear internal 'query' parameter
        query_filter = {}
        if active_only:
            query_filter["active"] = True
        
        if gender:
            # Case insensitive match for gender (e.g. 'female' or 'Female')
            query_filter["gender"] = {"$regex": f"^{gender}$", "$options": "i"}
            
        if is_verified is not None:
            query_filter["is_verified"] = is_verified

        # 3. Construct $geoNear stage
        # coordinates are longitude first, then latitude
        geo_near_options = {
            "near": {"type": "Point", "coordinates": [lng, lat]},
            "distanceField": "distance_meters",
            "spherical": True,
            "key": "_geoloc",
            "query": query_filter
        }

        # If a maximum search radius is provided, convert kilometers to meters
        if max_distance_km is not None and max_distance_km > 0:
            geo_near_options["maxDistance"] = max_distance_km * 1000.0

        # 4. Formulate Aggregation Pipeline with $facet for pagination metadata and data
        pipeline = [
            {
                "$geoNear": geo_near_options
            },
            {
                "$facet": {
                    "metadata": [
                        {"$count": "total"}
                    ],
                    "data": [
                        {"$skip": skip},
                        {"$limit": limit},
                        {
                            "$addFields": {
                                # Calculate kilometers dynamically from database meters
                                "distance_km": {"$divide": ["$distance_meters", 1000.0]}
                            }
                        }
                    ]
                }
            }
        ]

        logger.info(f"Executing nearby profile search with lat={lat}, lng={lng}, query_filter={query_filter}, page={page}, limit={limit}")
        
        try:
            cursor = collection.aggregate(pipeline)
            results = await cursor.to_list(length=1)
            
            if not results:
                return PaginatedResponse(data=[], total=0, page=page, limit=limit, has_more=False)
                
            facet_result = results[0]
            metadata = facet_result.get("metadata", [])
            data_list = facet_result.get("data", [])

            # Extract total count (if metadata is empty, it means 0 matches found)
            total = metadata[0]["total"] if metadata else 0
            
            # Map database documents to Pydantic responses
            profiles = []
            for doc in data_list:
                # MongoDB aggregation might return '_id' as standard string or UUID, 
                # Pydantic's alias and custom validator handle conversion smoothly.
                profiles.append(ProfileWithDistance.model_validate(doc))

            has_more = total > (skip + len(profiles))

            return PaginatedResponse(
                data=profiles,
                total=total,
                page=page,
                limit=limit,
                has_more=has_more
            )
            
        except Exception as e:
            logger.error(f"Error executing nearby profile search: {e}")
            raise e

    async def find_similar_profiles(
        self,
        profile_id: str,
        page: int = 1,
        limit: int = 10,
    ) -> PaginatedResponse[ProfileBase]:
        """
        Finds similar profiles for a given profile ID based on:
        - Opposite gender
        - Compatible height range (based on gender-specific rules)
        - Compatible birth date range (±6 years based on gender)
        - Exact marriage type match

        Male seeking Female:
            Height: female height_cm between (male_height - 20) and male_height
            Birth date: female birth_date between male_birth_date and male_birth_date + 6 years

        Female seeking Male:
            Height: male height_cm between female_height and (female_height + 30)
            Birth date: male birth_date between female_birth_date - 6 years and female_birth_date
        """
        collection = db_manager.get_collection()
        skip = (page - 1) * limit

        # 1. Fetch the source profile (IDs are stored as UUID strings, not ObjectId)
        source_doc = await collection.find_one({"_id": profile_id})

        if not source_doc:
            raise ValueError(f"Profile not found with ID: {profile_id}")

        source_gender = (source_doc.get("gender") or "").strip().lower()
        source_height_cm = source_doc.get("height_cm")
        source_birth_date = source_doc.get("birth_date")
        source_marriage_type = source_doc.get("type")

        if not source_gender:
            raise ValueError("Source profile does not have a gender specified.")

        # 2. Build the match filter for similar profiles
        match_filter = {
            "active": True,
            "_id": {"$ne": profile_id},  # Exclude the source profile
        }


        # Opposite gender
        if source_gender == "male":
            match_filter["gender"] = {"$regex": "^female$", "$options": "i"}
        else:
            match_filter["gender"] = {"$regex": "^male$", "$options": "i"}

        # Height range filter
        if source_height_cm is not None:
            if source_gender == "male":
                # Female height should be between (male_height - 20) and male_height
                height_lower = source_height_cm - 20
                height_upper = source_height_cm
                match_filter["height_cm"] = {"$gte": height_lower, "$lte": height_upper}
            else:
                # Male height should be between female_height and (female_height + 30)
                height_lower = source_height_cm
                height_upper = source_height_cm + 30
                match_filter["height_cm"] = {"$gte": height_lower, "$lte": height_upper}

        # Birth date range filter
        if source_birth_date is not None:
            # Ensure birth_date is a datetime object
            if isinstance(source_birth_date, str):
                try:
                    source_birth_date = datetime.fromisoformat(source_birth_date)
                except (ValueError, TypeError):
                    source_birth_date = None

            if source_birth_date is not None:
                if source_gender == "male":
                    # Female should be younger or up to 6 years younger than male
                    # birth_date between male_birth_date and male_birth_date + 6 years
                    date_lower = source_birth_date
                    date_upper = source_birth_date.replace(year=source_birth_date.year + 6)
                    match_filter["birth_date"] = {"$gte": date_lower, "$lte": date_upper}
                else:
                    # Male should be older or up to 6 years older than female
                    # birth_date between female_birth_date - 6 years and female_birth_date
                    date_lower = source_birth_date.replace(year=source_birth_date.year - 6)
                    date_upper = source_birth_date
                    match_filter["birth_date"] = {"$gte": date_lower, "$lte": date_upper}

        # Marriage type must match exactly (case-insensitive)
        if source_marriage_type:
            match_filter["type"] = {"$regex": f"^{source_marriage_type}$", "$options": "i"}

        # 3. Build the aggregation pipeline with $facet for pagination
        pipeline = [
            {"$match": match_filter},
            {
                "$facet": {
                    "metadata": [
                        {"$count": "total"}
                    ],
                    "data": [
                        {"$skip": skip},
                        {"$limit": limit},
                    ]
                }
            }
        ]

        logger.info(
            f"Executing similar profile search for profile_id={profile_id}, "
            f"gender={source_gender}, height_cm={source_height_cm}, "
            f"marriage_type={source_marriage_type}, page={page}, limit={limit}"
        )

        try:
            cursor = collection.aggregate(pipeline)
            results = await cursor.to_list(length=1)

            if not results:
                return PaginatedResponse(data=[], total=0, page=page, limit=limit, has_more=False)

            facet_result = results[0]
            metadata = facet_result.get("metadata", [])
            data_list = facet_result.get("data", [])

            total = metadata[0]["total"] if metadata else 0

            profiles = []
            for doc in data_list:
                profiles.append(ProfileBase.model_validate(doc))

            has_more = total > (skip + len(profiles))

            return PaginatedResponse(
                data=profiles,
                total=total,
                page=page,
                limit=limit,
                has_more=has_more
            )

        except Exception as e:
            logger.error(f"Error executing similar profile search: {e}")
            raise e

# Exported service singleton
profile_service = ProfileService()

