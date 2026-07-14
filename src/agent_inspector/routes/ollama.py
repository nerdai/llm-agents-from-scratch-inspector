"""Ollama daemon status route (see #18)."""

from fastapi import APIRouter

from agent_inspector.deps import OllamaServiceDep
from agent_inspector.schemas import OllamaStatusResponse

router = APIRouter()


@router.get("/ollama/status")
async def get_ollama_status(
    ollama_service: OllamaServiceDep,
) -> OllamaStatusResponse:
    """Report whether the local Ollama daemon is reachable.

    Never raises for an unreachable daemon -- the response is a
    normal ``200`` with ``reachable: False``, which the UI uses to
    show its ``ollama serve`` hint (see #18).

    Args:
        ollama_service (OllamaServiceDep): Injected Ollama service.

    Returns:
        OllamaStatusResponse: Whether the daemon responded, and its
            version if so.
    """
    reachable, version = await ollama_service.get_status()
    return OllamaStatusResponse(reachable=reachable, version=version)
