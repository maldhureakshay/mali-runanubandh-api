import logging
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from cachetools import TTLCache
from database import db_manager
from models.profile import ProfileBase, ProfileWithDistance
from models.common import PaginatedResponse

logger = logging.getLogger(__name__)

# In-memory cache for similar profiles results.
# Max 500 entries, each entry auto-expires after 24 hours (86400 seconds).
_similar_profiles_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)


class ProfileService:
    """
    ProfileService handles the business logic and MongoDB queries
    for geo-location matching, filtering, pagination, and similarity scoring.
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

    @staticmethod
    def _regex_match_either_direction(field: str, value: str) -> dict:
        """
        Returns a MongoDB expression (0 or 1) that scores 1 if either:
          - the candidate's `field` contains `value` as a substring, or
          - `value` contains the candidate's `field` as a substring.
        Both sides are matched case-insensitively via $regexMatch.
        Returns {"$literal": 0} when value is empty so the pipeline stays valid.
        """
        if not value:
            return {"$literal": 0}
        return {
            "$cond": [
                {
                    "$or": [
                        # candidate field contains source value
                        {
                            "$regexMatch": {
                                "input": {"$ifNull": [f"${field}", ""]},
                                "regex": value,
                                "options": "i",
                            }
                        },
                        # source value contains candidate field
                        {
                            "$regexMatch": {
                                "input": value,
                                "regex": {"$ifNull": [f"${field}", ""]},
                                "options": "i",
                            }
                        },
                    ]
                },
                1,
                0,
            ]
        }

    @staticmethod
    def _build_relevance_score_stage(source: dict) -> dict:
        """
        Builds a MongoDB $addFields stage that computes a relevance_score (0–10)
        for each candidate profile relative to the source profile.

        All text fields use case-insensitive substring matching (either direction),
        consistent with how job_location is matched.

        Scoring breakdown (max 10 points):
            +3  education_category  — substring match, case-insensitive
            +2  job_category        — substring match, case-insensitive
            +2  tag overlap         — any shared tag
            +2  education_subcategory — substring match, case-insensitive
            +1  job_location        — substring match, case-insensitive
        """
        source_edu_category    = (source.get("education_category")    or "").strip()
        source_edu_subcategory = (source.get("education_subcategory") or "").strip()
        source_job_category    = (source.get("job_category")          or "").strip()
        source_job_location    = (source.get("job_location")          or "").strip()
        source_tags: List[str] = source.get("tags") or []

        def regex_score(field: str, value: str, points: int) -> dict:
            """Wraps _regex_match_either_direction with a $multiply to apply points."""
            return {
                "$multiply": [
                    ProfileService._regex_match_either_direction(field, value),
                    points,
                ]
            }

        return {
            "$addFields": {
                "relevance_score": {
                    "$add": [
                        # +3 — education_category substring match
                        regex_score("education_category", source_edu_category, 3),

                        # +2 — job_category substring match
                        regex_score("job_category", source_job_category, 2),

                        # +2 — any shared tag
                        {
                            "$multiply": [
                                {
                                    "$cond": [
                                        {
                                            "$gt": [
                                                {
                                                    "$size": {
                                                        "$ifNull": [
                                                            {
                                                                "$setIntersection": [
                                                                    "$tags",
                                                                    source_tags,
                                                                ]
                                                            },
                                                            [],
                                                        ]
                                                    }
                                                },
                                                0,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                },
                                2,
                            ]
                        },

                        # +2 — education_subcategory substring match
                        regex_score("education_subcategory", source_edu_subcategory, 2),

                        # +1 — job_location substring match
                        regex_score("job_location", source_job_location, 1),
                    ]
                }
            }
        }

    async def find_nearby_profiles(
        self,
        lat: float,
        lng: float,
        page: int = 1,
        limit: int = 10,
        max_distance_km: Optional[float] = None,
        gender: Optional[str] = None,
        is_verified: Optional[bool] = None,
        active_only: bool = True,
    ) -> PaginatedResponse[ProfileWithDistance]:
        """
        Executes an aggregation query using MongoDB's $geoNear pipeline to find
        the nearest profiles to a given point. Integrates facet-based pagination
        to return total matched records and paginated data in a single DB request.
        """
        is_valid, error_msg = self.validate_coordinates(lat, lng)
        if not is_valid:
            raise ValueError(error_msg)

        collection = db_manager.get_collection()
        skip = (page - 1) * limit

        query_filter = {}
        if active_only:
            query_filter["active"] = True
        if gender:
            query_filter["gender"] = {"$regex": f"^{gender}$", "$options": "i"}
        if is_verified is not None:
            query_filter["is_verified"] = is_verified

        geo_near_options = {
            "near": {"type": "Point", "coordinates": [lng, lat]},
            "distanceField": "distance_meters",
            "spherical": True,
            "key": "_geoloc",
            "query": query_filter,
        }

        if max_distance_km is not None and max_distance_km > 0:
            geo_near_options["maxDistance"] = max_distance_km * 1000.0

        pipeline = [
            {"$geoNear": geo_near_options},
            {
                "$facet": {
                    "metadata": [{"$count": "total"}],
                    "data": [
                        {"$skip": skip},
                        {"$limit": limit},
                        {
                            "$addFields": {
                                "distance_km": {"$divide": ["$distance_meters", 1000.0]}
                            }
                        },
                    ],
                }
            },
        ]

        logger.info(
            f"Executing nearby profile search with lat={lat}, lng={lng}, "
            f"query_filter={query_filter}, page={page}, limit={limit}"
        )

        try:
            cursor = collection.aggregate(pipeline)
            results = await cursor.to_list(length=1)

            if not results:
                return PaginatedResponse(data=[], total=0, page=page, limit=limit, has_more=False)

            facet_result = results[0]
            metadata  = facet_result.get("metadata", [])
            data_list = facet_result.get("data", [])
            total     = metadata[0]["total"] if metadata else 0

            profiles = [ProfileWithDistance.model_validate(doc) for doc in data_list]
            has_more = total > (skip + len(profiles))

            return PaginatedResponse(
                data=profiles,
                total=total,
                page=page,
                limit=limit,
                has_more=has_more,
            )

        except Exception as e:
            logger.error(f"Error executing nearby profile search: {e}")
            raise

    async def find_similar_profiles(
        self,
        profile_id: str,
        page: int = 1,
        limit: int = 10,
    ) -> PaginatedResponse[ProfileBase]:
        """
        Finds similar profiles for a given profile ID based on:

        Demographic filters (hard):
            - Opposite gender
            - Compatible height range (gender-specific rules)
            - Compatible birth date range (±6 years, gender-specific)
            - Exact marriage type match

        Relevance scoring (soft — higher score = better match, max 10):
            - +3  education_category  substring match, case-insensitive
            - +2  job_category        substring match, case-insensitive
            - +2  any overlapping tag
            - +2  education_subcategory substring match, case-insensitive
            - +1  job_location        substring match, case-insensitive

        Results are sorted by relevance_score DESC, then listing_rand ASC
        for variety within the same score tier.

        Male seeking Female:
            Height: female height_cm between (male_height - 20) and male_height
            Birth date: female birth_date between male_birth_date and male_birth_date + 6 years

        Female seeking Male:
            Height: male height_cm between female_height and (female_height + 30)
            Birth date: male birth_date between female_birth_date - 6 years and female_birth_date
        """
        cache_key = (profile_id, page, limit)
        if cache_key in _similar_profiles_cache:
            logger.info(
                f"Cache hit — similar profiles for profile_id={profile_id}, "
                f"page={page}, limit={limit}"
            )
            return _similar_profiles_cache[cache_key]

        collection = db_manager.get_collection()
        skip = (page - 1) * limit

        # 1. Fetch source profile
        source_doc = await collection.find_one({"_id": profile_id})
        if not source_doc:
            raise ValueError(f"Profile not found with ID: {profile_id}")

        source_gender        = (source_doc.get("gender") or "").strip().lower()
        source_height_cm     = source_doc.get("height_cm")
        source_birth_date    = source_doc.get("birth_date")
        source_marriage_type = source_doc.get("type")

        if not source_gender:
            raise ValueError("Source profile does not have a gender specified.")

        # 2. Build hard-filter match stage
        match_filter: dict = {
            "active": True,
            "_id": {"$ne": profile_id},
        }

        # Opposite gender
        if source_gender == "male":
            match_filter["gender"] = {"$regex": "^female$", "$options": "i"}
        else:
            match_filter["gender"] = {"$regex": "^male$", "$options": "i"}

        # Height range filter
        if source_height_cm is not None:
            if source_gender == "male":
                match_filter["height_cm"] = {
                    "$gte": source_height_cm - 20,
                    "$lte": source_height_cm,
                }
            else:
                match_filter["height_cm"] = {
                    "$gte": source_height_cm,
                    "$lte": source_height_cm + 30,
                }

        # Birth date range filter
        if source_birth_date is not None:
            if isinstance(source_birth_date, str):
                try:
                    source_birth_date = datetime.fromisoformat(source_birth_date)
                except (ValueError, TypeError):
                    source_birth_date = None

            if source_birth_date is not None:
                if source_gender == "male":
                    date_lower = source_birth_date - timedelta(days=90)
                    date_upper = source_birth_date.replace(year=source_birth_date.year + 6)
                else:
                    date_lower = source_birth_date.replace(year=source_birth_date.year - 6)
                    date_upper = source_birth_date + timedelta(days=90)

                match_filter["birth_date"] = {"$gte": date_lower, "$lte": date_upper}

        # Marriage type match (case-insensitive, strip trailing spaces from raw data)
        if source_marriage_type:
            match_filter["type"] = {
                "$regex": f"^{source_marriage_type.strip()}$",
                "$options": "i",
            }

        # 3. Build scoring stage
        relevance_score_stage = self._build_relevance_score_stage(source_doc)

        logger.info(
            f"Executing similar profile search — profile_id={profile_id}, "
            f"gender={source_gender}, height_cm={source_height_cm}, "
            f"education_category={source_doc.get('education_category')}, "
            f"education_subcategory={source_doc.get('education_subcategory')}, "
            f"job_category={source_doc.get('job_category')}, "
            f"job_location={source_doc.get('job_location')}, "
            f"tags={source_doc.get('tags')}, "
            f"marriage_type={source_marriage_type}, page={page}, limit={limit}"
        )

        # 4. Aggregation pipeline
        pipeline = [
            {"$match": match_filter},
            relevance_score_stage,
            {"$sort": {"relevance_score": -1, "listing_rand": 1}},
            {
                "$facet": {
                    "metadata": [{"$count": "total"}],
                    "data": [
                        {"$skip": skip},
                        {"$limit": limit},
                    ],
                }
            },
        ]

        try:
            cursor = collection.aggregate(pipeline)
            results = await cursor.to_list(length=1)

            if not results:
                return PaginatedResponse(data=[], total=0, page=page, limit=limit, has_more=False)

            facet_result = results[0]
            metadata  = facet_result.get("metadata", [])
            data_list = facet_result.get("data", [])
            total     = metadata[0]["total"] if metadata else 0

            profiles = [ProfileBase.model_validate(doc) for doc in data_list]
            has_more = total > (skip + len(profiles))

            response = PaginatedResponse(
                data=profiles,
                total=total,
                page=page,
                limit=limit,
                has_more=has_more,
            )
            _similar_profiles_cache[cache_key] = response
            return response

        except Exception as e:
            logger.error(f"Error executing similar profile search: {e}")
            raise

    def invalidate_similar_profiles_cache(self, profile_id: Optional[str] = None) -> None:
        """
        Invalidates the similar profiles cache.
        If profile_id is provided, only entries for that profile are removed.
        Otherwise, the entire cache is cleared.
        """
        if profile_id:
            keys_to_delete = [k for k in _similar_profiles_cache if k[0] == profile_id]
            for k in keys_to_delete:
                del _similar_profiles_cache[k]
            logger.info(f"Invalidated similar profiles cache for profile_id={profile_id}")
        else:
            _similar_profiles_cache.clear()
            logger.info("Invalidated entire similar profiles cache")


# Exported singleton
profile_service = ProfileService()