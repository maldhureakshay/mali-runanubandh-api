"""
Health checking subpackage.

Provides router for liveness and readiness probes.
"""

from app.platform.health.health_check import router as health_router
