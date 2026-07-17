"""Shared domain-exception -> HTTP-response mapping (see #26).

Before this, every mutating route in ``routes/session.py`` duplicated
the same handful of ``try/except SomeSessionServiceError: raise
HTTPException(status_code=..., detail=str(e))`` blocks -- the mapping
from domain exception type to status code was identical across almost
every route, just repeated. Registering one exception handler on the
``FastAPI`` app (via ``register_exception_handlers``, called from
``server.create_app``) consolidates that into a single table, so every
route can simply let a ``SessionServiceError`` propagate and this
module maps it consistently, in one place, to a ``404``/``409``/``422``/
``502``/``500`` response with the same envelope shape FastAPI's own
``HTTPException`` produces (``{"detail": "..."}"``).
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from agent_inspector.errors.session import (
    AgentBuilderNotConfiguredError,
    AgentBuildError,
    InvalidNeedTransitionError,
    MissingPendingResultError,
    MissingRolloutSpanError,
    NoEditableResultError,
    NoPendingStepError,
    SessionBusyError,
    SessionConfigError,
    SessionNotFoundError,
    SessionServiceError,
    StepExecutionError,
    ToolExecutionError,
    WrongNeedError,
)

# Every SessionServiceError subclass's docstring already states the
# status code its route mapping should use -- this table is the single
# place that actually applies it. Exceptions not listed here (a bug,
# since every current subclass is listed) fall back to 500 in the
# handler below rather than raising a KeyError.
#
# Keyed by `type[Exception]` rather than `type[SessionServiceError]`
# so `_STATUS_CODES.get(type(exc), ...)` below type-checks directly:
# `exc` is statically typed `Exception` (see that function's
# docstring for why), and mypy infers `type(exc)` as `type[Exception]`
# accordingly, not the narrower `type[SessionServiceError]` this
# table's keys actually are at runtime.
_STATUS_CODES: dict[type[Exception], int] = {
    SessionNotFoundError: status.HTTP_404_NOT_FOUND,
    SessionBusyError: status.HTTP_409_CONFLICT,
    WrongNeedError: status.HTTP_409_CONFLICT,
    InvalidNeedTransitionError: status.HTTP_409_CONFLICT,
    NoEditableResultError: status.HTTP_409_CONFLICT,
    SessionConfigError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NoPendingStepError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    MissingPendingResultError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    MissingRolloutSpanError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    AgentBuilderNotConfiguredError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    AgentBuildError: status.HTTP_502_BAD_GATEWAY,
    StepExecutionError: status.HTTP_502_BAD_GATEWAY,
    ToolExecutionError: status.HTTP_502_BAD_GATEWAY,
}


async def _session_service_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Translate any ``SessionServiceError`` into a JSON error response.

    Typed ``exc: Exception`` (rather than ``SessionServiceError``) to
    match Starlette's ``ExceptionHandler`` signature
    (``Callable[[Request, Exception], Response | Awaitable[Response]]``)
    exactly -- ``add_exception_handler`` is only ever called below with
    ``SessionServiceError`` as the registered class, so ``exc`` is
    always actually a ``SessionServiceError`` at runtime; the wider
    static type is just what the registration API requires.

    Looked up by exact type against ``_STATUS_CODES`` (not
    ``isinstance``): every current subclass is a leaf class with no
    further subclasses of its own, so exact-type lookup is simplest
    and correct; it also fails safe (falls back to ``500``, not a
    lookup crash) if a future subclass is added here without being
    added to the table.

    Args:
        request (Request): The request that raised (required by
            FastAPI's exception-handler signature; unused).
        exc (Exception): The domain exception raised by
            ``services/session.py`` (always a ``SessionServiceError``
            in practice -- see above).

    Returns:
        JSONResponse: Same ``{"detail": "<message>"}`` envelope shape
            as FastAPI's own ``HTTPException`` responses, at the
            status code ``_STATUS_CODES`` maps ``exc``'s type to.
    """
    status_code = _STATUS_CODES.get(
        type(exc),
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


def register_exception_handlers(app: FastAPI) -> None:
    """Register the shared ``SessionServiceError`` handler on ``app``.

    Args:
        app (FastAPI): The application to register handlers on.
    """
    app.add_exception_handler(
        SessionServiceError,
        _session_service_error_handler,
    )
