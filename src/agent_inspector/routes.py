"""API route registration.

Routes are intentionally thin: parse the request, call the relevant
service via its injected dependency, map any domain exception to an
appropriate ``HTTPException``, and return. No business logic lives
here — see ``services.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from agent_inspector.deps import HealthServiceDep, SessionServiceDep
from agent_inspector.services import (
    MissingPendingResultError,
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
