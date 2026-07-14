"""FastAPI dependency-injection providers.

This is the only module that wires up FastAPI's ``Depends`` machinery.
Both services and routes receive their collaborators through the
``Annotated`` aliases defined here (e.g. ``HealthServiceDep``), keeping
DI wiring in one place as the app grows more services.
"""

from typing import Annotated

from fastapi import Depends
from llm_agents_from_scratch import LLMAgentBuilder

from agent_inspector.services.health import HealthService
from agent_inspector.services.ollama import OllamaService
from agent_inspector.services.session import SessionService

_health_service = HealthService()


def get_health_service() -> HealthService:
    """Provide the process-wide ``HealthService`` instance.

    Returns:
        HealthService: The shared health service instance.
    """
    return _health_service


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]

_ollama_service = OllamaService()


def get_ollama_service() -> OllamaService:
    """Provide the process-wide ``OllamaService`` instance.

    Returns:
        OllamaService: The shared Ollama service instance.
    """
    return _ollama_service


OllamaServiceDep = Annotated[OllamaService, Depends(get_ollama_service)]

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


def configure_agent_builder(agent_builder: LLMAgentBuilder) -> None:
    """Wire the CLI-discovered ``LLMAgentBuilder`` into the shared service.

    Called once by ``cli.py``'s ``launch`` command, after discovery
    (see ``discovery.py``) succeeds and before the app starts serving
    requests -- ``SessionService.create_session_from_config`` needs a
    real builder to construct agents from (see ADR-002).

    Args:
        agent_builder (LLMAgentBuilder): The builder discovered from
            the user's entrypoint script.
    """
    _session_service.agent_builder = agent_builder


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
