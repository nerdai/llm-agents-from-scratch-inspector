"""FastAPI dependency-injection providers.

This is the only module that wires up FastAPI's ``Depends`` machinery.
Both services and routes receive their collaborators through the
``Annotated`` aliases defined here (e.g. ``HealthServiceDep``), keeping
DI wiring in one place as the app grows more services.
"""

from typing import Annotated

from fastapi import Depends

from agent_inspector.services.health import HealthService
from agent_inspector.services.session import SessionService

_health_service = HealthService()


def get_health_service() -> HealthService:
    """Provide the process-wide ``HealthService`` instance.

    Returns:
        HealthService: The shared health service instance.
    """
    return _health_service


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]

# Module-level singleton: SessionService holds live in-memory session
# state (agents, handlers, locks), so it must not be re-created per
# request the way a stateless service could be.
_session_service = SessionService()


def get_session_service() -> SessionService:
    """Provide the process-wide ``SessionService`` instance.

    Returns:
        SessionService: The shared session service instance.
    """
    return _session_service


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
