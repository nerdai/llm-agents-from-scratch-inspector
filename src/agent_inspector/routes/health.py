"""Health-check route (see #1)."""

from fastapi import APIRouter

from agent_inspector.deps import HealthServiceDep

router = APIRouter()


@router.get("/health")
def get_health(health_service: HealthServiceDep) -> dict[str, str]:
    """Report backend liveness.

    Args:
        health_service (HealthServiceDep): Injected health service.

    Returns:
        dict[str, str]: A status payload, e.g. ``{"status": "ok"}``.
    """
    return health_service.check()
