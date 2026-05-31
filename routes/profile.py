from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status
from services.profile_service import profile_service
from models.profile import ProfileWithDistance
from models.common import PaginatedResponse
from database import db_manager

router = APIRouter(prefix="/api/profiles", tags=["Profiles"])

@router.get(
    "/nearby",
    response_model=PaginatedResponse[ProfileWithDistance],
    response_model_by_alias=False,
    summary="Find nearest profiles",
    description="Calculates distances and returns active matrimony profiles ordered nearest to farthest with pagination."
)
async def get_nearby_profiles(
    lat: float = Query(
        ..., 
        description="Current user's latitude (degrees)", 
        ge=-90.0, 
        le=90.0,
        examples=[18.5204]
    ),
    lng: float = Query(
        ..., 
        description="Current user's longitude (degrees)", 
        ge=-180.0, 
        le=180.0,
        examples=[73.8567]
    ),
    page: int = Query(
        1, 
        description="Page number for pagination", 
        ge=1
    ),
    limit: int = Query(
        10, 
        description="Number of profiles to retrieve per page (max 100)", 
        ge=1, 
        le=100
    ),
    max_distance_km: Optional[float] = Query(
        None, 
        description="Filter profiles within a maximum radial distance (km)", 
        gt=0.0
    ),
    gender: Optional[str] = Query(
        None, 
        description="Filter profiles by gender ('male', 'female')", 
        pattern="^(male|female|MALE|FEMALE)$"
    ),
    is_verified: Optional[bool] = Query(
        None, 
        description="Filter profiles based on verification status"
    )
):
    try:
        paginated_result = await profile_service.find_nearby_profiles(
            lat=lat,
            lng=lng,
            page=page,
            limit=limit,
            max_distance_km=max_distance_km,
            gender=gender,
            is_verified=is_verified
        )
        return paginated_result
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching profiles: {str(exc)}"
        )

@router.get(
    "/health",
    summary="Service Health Check",
    description="Validates API container status and verifies active MongoDB connectivity."
)
async def health_check():
    """
    Exposes a quick health check endpoint validating MongoDB status.
    """
    is_db_healthy = await db_manager.check_health()
    if not is_db_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "database": "disconnected"}
        )
    return {"status": "healthy", "database": "connected"}
