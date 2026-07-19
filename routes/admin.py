from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status
from services.user_service import user_service
from models.user import UserBase
from models.common import PaginatedResponse

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.get(
    "/users",
    response_model=PaginatedResponse[UserBase],
    response_model_by_alias=False,
    summary="Get all users",
    description="Returns all users from the users collection with pagination and optional phone search, latest first."
)
async def get_users(
    page: int = Query(
        1,
        description="Page number for pagination",
        ge=1
    ),
    limit: int = Query(
        10,
        description="Number of users to retrieve per page (max 100)",
        ge=1,
        le=100
    ),
    phone: Optional[str] = Query(
        None,
        description="Optional phone number filter (partial match)"
    )
):
    try:
        paginated_result = await user_service.find_users(
            page=page,
            limit=limit,
            phone=phone
        )
        return paginated_result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching users: {str(exc)}"
        )

@router.get(
    "/dashboard",
    summary="Get dashboard metrics",
    description="Returns aggregate dashboard statistics: total/active users and profiles."
)
async def get_dashboard(
    active_since: Optional[datetime] = Query(
        None,
        description="Optional cutoff date to count active users created after/on this date (e.g. 2026-02-09T00:00:00Z)"
    )
):
    try:
        metrics = await user_service.get_dashboard_metrics(active_since_cutoff=active_since)
        return metrics
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while loading dashboard metrics: {str(exc)}"
        )
