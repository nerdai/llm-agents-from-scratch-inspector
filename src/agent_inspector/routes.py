"""API route registration.

Routes are intentionally thin: parse the request, call the relevant
service via its injected dependency, map any domain exception to an
appropriate ``HTTPException``, and return. No business logic lives
here — see ``services.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agent_inspector.deps import HealthServiceDep, SessionServiceDep
from agent_inspector.services import NEXT_NUMBER_TOOL_NAME, SessionConfigError

router = APIRouter(prefix="/api")


@router.get("/health")
def get_health(health_service: HealthServiceDep) -> dict[str, str]:
    """Report backend liveness.

    Args:
        health_service (HealthServiceDep): Injected health service.

    Returns:
        dict[str, str]: A status payload, e.g. ``{"status": "ok"}``.
    """
    return health_service.check()


class FunctionToolSpec(BaseModel):
    """A client-supplied function-tool description.

    M1 (issue #3) accepts these but only ever registers the hardcoded
    ``next_number`` tool -- see ``agent_inspector.services``. Genuine
    arbitrary function-tool registration is issue #8 (M2).
    """

    name: str
    signature: str | None = None
    source: str | None = None


class CreateSessionRequest(BaseModel):
    """Request body for ``POST /api/sessions`` (TRD §6.1).

    M1 only acts on ``task``, ``model``, and ``think``.
    ``skills_scopes``/``explicit_only_skills``/``mcp_servers`` are
    M2/M3 scope: accepted here so well-formed clients don't get a
    spurious ``422``, but not wired up to anything yet.
    """

    task: str = Field(min_length=1)
    model: str | None = None
    think: bool | None = None
    function_tools: list[FunctionToolSpec] | None = None
    skills_scopes: list[str] | None = None
    explicit_only_skills: list[str] | None = None
    mcp_servers: list[dict[str, Any]] | None = None


class TaskOut(BaseModel):
    """The ``task`` portion of a ``CreateSessionResponse``."""

    id_: str
    instruction: str


class CreateSessionResponse(BaseModel):
    """Response body for ``POST /api/sessions`` (TRD §6.1)."""

    session_id: str
    task: TaskOut
    tools: list[str]
    skills: list[Any] = []
    need: str


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    request: CreateSessionRequest,
    session_service: SessionServiceDep,
) -> CreateSessionResponse:
    """Create a new supervised-run session (TRD §6.1).

    Builds an ``LLMAgent`` per the request config and starts a
    ``run_supervised()`` handler for it, then registers the session.

    Args:
        request (CreateSessionRequest): The session config to create.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        CreateSessionResponse: The new session's id, task, tools,
            skills, and initial ``need`` (always ``"next"``).

    Raises:
        HTTPException: ``422`` if the request config is invalid.
    """
    try:
        session = await session_service.create_session_from_config(
            task=request.task,
            model=request.model,
            think=request.think,
            function_tools=[ft.name for ft in request.function_tools or []],
        )
    except SessionConfigError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=e.message,
        ) from e

    task = session.handler.task
    return CreateSessionResponse(
        session_id=session.id,
        task=TaskOut(id_=task.id_, instruction=task.instruction),
        tools=[NEXT_NUMBER_TOOL_NAME],
        skills=[],
        need=session.need,
    )
