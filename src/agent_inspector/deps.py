"""FastAPI dependency-injection providers.

This is the only module that wires up FastAPI's ``Depends`` machinery.
Both services and routes receive their collaborators through the
``Annotated`` aliases defined here (e.g. ``HealthServiceDep``), keeping
DI wiring in one place as the app grows more services.
"""

from typing import Annotated

from fastapi import Depends

from agent_inspector.services import HealthService

_health_service = HealthService()


def get_health_service() -> HealthService:
    """Provide the process-wide ``HealthService`` instance.

    Returns:
        HealthService: The shared health service instance.
    """
    return _health_service


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
