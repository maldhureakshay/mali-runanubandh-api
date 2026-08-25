"""
Health endpoints router.

Exposes status endpoints:
- GET /health
- GET /health/live
- GET /health/ready (verifies MongoDB and Firebase Admin status)
"""

from fastapi import APIRouter, Response, status
import firebase_admin

from database import db_manager

router = APIRouter(prefix="/health")


@router.get(
    "",
    summary="Health check",
    description="Simple health endpoint returning status healthy."
)
async def health_root():
    """General health check."""
    return {"status": "healthy"}


@router.get(
    "/live",
    summary="Liveness check",
    description="Verifies that the application process is running and accepting requests."
)
async def liveness():
    """Liveness probe."""
    return {"status": "alive"}


@router.get(
    "/ready",
    summary="Readiness check",
    description="Verifies backing infrastructure readiness (MongoDB connectivity and Firebase initialization)."
)
async def readiness(response: Response):
    """Readiness probe."""
    mongo_ok = False
    try:
        mongo_ok = await db_manager.check_health()
    except Exception:
        mongo_ok = False

    firebase_ok = False
    try:
        firebase_admin.get_app()
        firebase_ok = True
    except ValueError:
        firebase_ok = False

    if mongo_ok and firebase_ok:
        return {
            "status": "ready",
            "dependencies": {
                "mongodb": "connected",
                "firebase": "initialized"
            }
        }
    
    # Degraded or offline
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "not_ready",
        "dependencies": {
            "mongodb": "connected" if mongo_ok else "disconnected",
            "firebase": "initialized" if firebase_ok else "uninitialized"
        }
    }
