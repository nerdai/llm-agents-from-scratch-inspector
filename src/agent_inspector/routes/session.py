"""Session lifecycle routes (see #3-#6).

Routes are intentionally thin: parse the request, call the relevant
service via its injected dependency, map any domain exception to an
appropriate ``HTTPException``, and return. No business logic lives
here -- see ``services/session.py``.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agent_inspector.deps import SessionServiceDep
from agent_inspector.errors import (
    MissingPendingResultError,
    NoPendingStepError,
    SessionBusyError,
    SessionConfigError,
    SessionNotFoundError,
    StepExecutionError,
    WrongNeedError,
)
from agent_inspector.services.session import (
    NEXT_NUMBER_TOOL_NAME,
    Need,
    NextStepDecisionOutcome,
)

router = APIRouter()


class FunctionToolSpec(BaseModel):
    """A client-supplied function-tool description.

    M1 (issue #3) accepts these but only ever registers the hardcoded
    ``next_number`` tool -- see ``agent_inspector.services.session``.
    Genuine arbitrary function-tool registration is issue #8 (M2).
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


@router.post("/sessions/{session_id}/next-step")
async def post_next_step(
    session_id: str,
    session_service: SessionServiceDep,
) -> dict[str, Any]:
    """Advance a session to its next step or final result (TRD §6.2).

    No request body: the server tracks the previous step result
    internally on the session rather than the client supplying it
    (see ``services.session.Session.last_step_result``).

    Args:
        session_id (str): The session identifier.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        dict[str, Any]: ``{"kind": "next_step", "decision": {...},
            "step": {...}, "need": "run"}`` when the handler produced
            another step, or ``{"kind": "final_result", "result":
            {...}, "need": "approve"}`` when it produced the task's
            final result.

    Raises:
        HTTPException: 404 if ``session_id`` is unknown; 409 if the
            session isn't currently waiting on ``next`` or already
            has another mutating call in flight.
    """
    try:
        outcome = await session_service.get_next_step(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (WrongNeedError, SessionBusyError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    if isinstance(outcome, NextStepDecisionOutcome):
        return {
            "kind": outcome.kind,
            "decision": outcome.decision.model_dump(),
            "step": outcome.step.model_dump(),
            "need": outcome.need,
        }

    return {
        "kind": outcome.kind,
        "result": outcome.result.model_dump(),
        "need": outcome.need,
    }


class TaskStepResultOut(BaseModel):
    """Wire representation of the framework's ``TaskStepResult``."""

    task_step_id: str
    content: str


class ToolCallTraceOut(BaseModel):
    """Wire representation of one executed tool call."""

    tool_name: str
    args: dict[str, Any]
    content: Any
    error: bool


class RunStepResponse(BaseModel):
    """Response body for ``POST /api/sessions/{id}/run-step`` (see #5)."""

    result: TaskStepResultOut
    tool_calls: list[ToolCallTraceOut]
    step_counter: int
    need: Need


@router.post("/sessions/{session_id}/run-step")
async def post_run_step(
    session_id: str,
    session_service: SessionServiceDep,
) -> RunStepResponse:
    """Execute the session's pending ``TaskStep`` (TRD §6.3, see #5).

    No request body: executes whatever ``TaskStep`` is currently
    pending on the session (recorded by the next-step endpoint, #4).
    Requires ``need == "run"``.

    Args:
        session_id (str): The session identifier.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        RunStepResponse: The step result, tool-call trace, updated
            step counter, and resulting ``need`` (``"next"`` on
            success).

    Raises:
        HTTPException: ``404`` if the session doesn't exist, ``409``
            if the session is busy or not waiting on ``need == "run"``,
            ``502`` if the framework raises while executing the step
            (LLM/framework-level failure), ``500`` on a server
            invariant violation (``need == "run"`` with no pending
            step recorded).
    """
    try:
        with session_service.lock_session(session_id) as session:
            outcome = await session_service.run_step(session)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except SessionBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except WrongNeedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except StepExecutionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except NoPendingStepError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return RunStepResponse(
        result=TaskStepResultOut(
            task_step_id=outcome.result.task_step_id,
            content=outcome.result.content,
        ),
        tool_calls=[
            ToolCallTraceOut(
                tool_name=trace.tool_name,
                args=trace.args,
                content=trace.content,
                error=trace.error,
            )
            for trace in outcome.tool_calls
        ],
        step_counter=outcome.step_counter,
        need=outcome.need,
    )


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: str,
    session_service: SessionServiceDep,
) -> dict[str, Any]:
    """Approve the session's pending ``TaskResult`` (TRD §6.4, see #6).

    No request body is needed: the server already holds the pending
    ``TaskResult`` produced by the ``next-step`` call that put the
    session into ``need="approve"``.

    Args:
        session_id (str): The session identifier.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        dict[str, Any]: ``{"status": "resolved", "result": {"task_id":
            ..., "content": ...}, "need": "done"}``.

    Raises:
        HTTPException: ``404`` if the session doesn't exist, ``409``
            if the session isn't at ``need="approve"`` or already has
            a call in flight, ``500`` if the session reached
            ``need="approve"`` without a pending result stored (a
            server-side bug elsewhere in the ``need`` orchestration).
    """
    try:
        with session_service.lock_session(session_id) as session:
            result = await session_service.complete(session)
            need = session.need
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (SessionBusyError, WrongNeedError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except MissingPendingResultError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "status": "resolved",
        "result": {"task_id": result.task_id, "content": result.content},
        "need": need,
    }
