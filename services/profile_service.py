import logging
import random
from collections import defaultdict
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from cachetools import TTLCache
from database import db_manager
from models.profile import ProfileBase, ProfileWithDistance
from models.common import PaginatedResponse

logger = logging.getLogger(__name__)

# In-memory cache for daily recommendation IDs.
# Keyed by profile_id → list of (candidate_id, relevance_score) tuples.
# Max 500 entries, each entry auto-expires after 24 hours (86400 seconds).
_daily_recommendations_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)

# Maximum number of diverse recommendations to pre-select per profile per day.
_MAX_DAILY_RECOMMENDATIONS = 20


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

    @staticmethod
    def _select_diverse_profiles(
        candidates: List[dict],
        max_profiles: int = _MAX_DAILY_RECOMMENDATIONS,
    ) -> List[Tuple[str, int]]:
        """
        Groups candidates by relevance_score and randomly selects from each
        bucket using geometric decay — higher-score buckets get approximately
        half of the remaining slots each round, guaranteeing that lower-score
        profiles also appear in the final set.

        Returns a list of (profile_id, relevance_score) tuples ordered by
        descending score (within each bucket the order is random).
        """
        if not candidates:
            return []

        # Group by integer relevance_score
        buckets: dict[int, List[str]] = defaultdict(list)
        for c in candidates:
            score = int(c.get("relevance_score", 0))
            buckets[score].append(c["_id"])

        sorted_scores = sorted(buckets.keys(), reverse=True)
        selected: List[Tuple[str, int]] = []
        remaining = max_profiles

        # First pass — geometric decay: take ~50 % of remaining slots per bucket
        for score in sorted_scores:
            if remaining <= 0:
                break
            pool = buckets[score]
            take = min(len(pool), max(1, remaining // 2))
            chosen = random.sample(pool, take)
            selected.extend((pid, score) for pid in chosen)
            # Remove chosen from pool so second pass can use leftovers
            buckets[score] = [p for p in pool if p not in set(chosen)]
            remaining -= take

        # Second pass — fill any remaining slots from unused candidates
        if remaining > 0:
            leftovers: List[Tuple[str, int]] = []
            for score in sorted_scores:
                for pid in buckets[score]:
                    leftovers.append((pid, score))
            if leftovers:
                extra = random.sample(leftovers, min(len(leftovers), remaining))
                selected.extend(extra)

        return selected

    async def _build_daily_recommendations(
        self,
        profile_id: str,
    ) -> List[Tuple[str, int]]:
        """
        Runs the full compatibility pipeline (filters + scoring), then
        selects a diverse set of up to 20 profiles using score-bucket
        sampling.  The result is cached for 24 hours.
        """
        collection = db_manager.get_collection()

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
            f"Building daily recommendations — profile_id={profile_id}, "
            f"gender={source_gender}, height_cm={source_height_cm}, "
            f"education_category={source_doc.get('education_category')}, "
            f"education_subcategory={source_doc.get('education_subcategory')}, "
            f"job_category={source_doc.get('job_category')}, "
            f"job_location={source_doc.get('job_location')}, "
            f"tags={source_doc.get('tags')}, "
            f"marriage_type={source_marriage_type}"
        )

        # 4. Aggregation — fetch scored candidates (capped at 200)
        pipeline = [
            {"$match": match_filter},
            relevance_score_stage,
            {"$sort": {"relevance_score": -1}},
            {"$limit": 200},
            {"$project": {"_id": 1, "relevance_score": 1}},
        ]

        try:
            cursor = collection.aggregate(pipeline)
            all_candidates = await cursor.to_list(length=200)
        except Exception as e:
            logger.error(f"Error fetching candidates for daily recommendations: {e}")
            raise

        # 5. Score-bucket random selection
        selected = self._select_diverse_profiles(all_candidates)

        # 6. Cache the selected IDs for 24 hours
        _daily_recommendations_cache[profile_id] = selected
        logger.info(
            f"Cached {len(selected)} daily recommendations for "
            f"profile_id={profile_id}"
        )

        return selected

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

        Daily diversity:
            On the first request each day (or when the 24-hour cache expires),
            up to 20 profiles are randomly selected from score-grouped buckets
            using geometric decay — higher scores are preferred but lower-score
            profiles are also included for variety.  Subsequent requests within
            the same 24-hour window always return the same set, paginated.

        Male seeking Female:
            Height: female height_cm between (male_height - 20) and male_height
            Birth date: female birth_date between male_birth_date and male_birth_date + 6 years

        Female seeking Male:
            Height: male height_cm between female_height and (female_height + 30)
            Birth date: male birth_date between female_birth_date - 6 years and female_birth_date
        """
        collection = db_manager.get_collection()
        skip = (page - 1) * limit

        # --- Resolve daily recommendation set (cached or freshly generated) ---
        if profile_id in _daily_recommendations_cache:
            recommendations = _daily_recommendations_cache[profile_id]
            logger.info(
                f"Cache hit — daily recommendations for profile_id={profile_id}, "
                f"page={page}, limit={limit}"
            )
        else:
            recommendations = await self._build_daily_recommendations(profile_id)

        total = len(recommendations)

        # --- Paginate over the pre-selected recommendation IDs ---
        page_slice = recommendations[skip : skip + limit]
        if not page_slice:
            return PaginatedResponse(
                data=[], total=total, page=page, limit=limit, has_more=False
            )

        page_ids = [pid for pid, _score in page_slice]
        score_map = {pid: score for pid, score in page_slice}

        try:
            # Fetch full profile documents for this page
            docs = await collection.find({"_id": {"$in": page_ids}}).to_list(
                length=limit
            )

            # Re-attach relevance_score and preserve the cached order
            doc_map: dict = {}
            for doc in docs:
                doc["relevance_score"] = score_map.get(doc["_id"])
                doc_map[doc["_id"]] = doc

            ordered_docs = [doc_map[pid] for pid in page_ids if pid in doc_map]
            profiles = [ProfileBase.model_validate(doc) for doc in ordered_docs]
            has_more = total > (skip + len(profiles))

            return PaginatedResponse(
                data=profiles,
                total=total,
                page=page,
                limit=limit,
                has_more=has_more,
            )

        except Exception as e:
            logger.error(f"Error executing similar profile search: {e}")
            raise

    def invalidate_similar_profiles_cache(self, profile_id: Optional[str] = None) -> None:
        """
        Invalidates the daily recommendations cache.
        If profile_id is provided, only the entry for that profile is removed.
        Otherwise, the entire cache is cleared.
        """
        if profile_id:
            if profile_id in _daily_recommendations_cache:
                del _daily_recommendations_cache[profile_id]
            logger.info(f"Invalidated daily recommendations cache for profile_id={profile_id}")
        else:
            _daily_recommendations_cache.clear()
            logger.info("Invalidated entire daily recommendations cache")


# Exported singleton
profile_service = ProfileService()