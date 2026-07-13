"""API route registration.

Routes are intentionally thin: parse the request, call the relevant
service via its injected dependency, map any domain exception to an
appropriate ``HTTPException``, and return. No business logic lives
here — see ``services.py``.
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from agent_inspector.deps import HealthServiceDep, SessionServiceDep
from agent_inspector.services import (
    NextStepDecisionOutcome,
    SessionBusyError,
    SessionNotFoundError,
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


@router.post("/sessions/{session_id}/next-step")
async def post_next_step(
    session_id: str,
    session_service: SessionServiceDep,
) -> dict[str, Any]:
    """Advance a session to its next step or final result (TRD §6.2).

    No request body: the server tracks the previous step result
    internally on the session rather than the client supplying it
    (see ``services.Session.last_step_result``).

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
