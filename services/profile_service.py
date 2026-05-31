import logging
from typing import Optional, List, Tuple
from database import db_manager
from models.profile import ProfileWithDistance
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

# Exported service singleton
profile_service = ProfileService()
