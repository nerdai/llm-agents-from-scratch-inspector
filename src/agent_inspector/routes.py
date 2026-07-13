"""API route registration.

Routes are intentionally thin: parse the request, call the relevant
service via its injected dependency, map any domain exception to an
appropriate ``HTTPException``, and return. No business logic lives
here — see ``services.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent_inspector.deps import HealthServiceDep, SessionServiceDep
from agent_inspector.services import (
    Need,
    NoPendingStepError,
    SessionBusyError,
    SessionNotFoundError,
    StepExecutionError,
    WrongNeedError,
)

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
