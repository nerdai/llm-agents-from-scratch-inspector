"""Business-logic services for Agent Inspector.

This module is the only place domain/business logic lives. Routes
(``routes.py``) call into services through the dependency-injected
instances declared in ``deps.py``; services raise domain exceptions
rather than ``fastapi.HTTPException``, leaving HTTP-status mapping to
the route layer.

This module contains ``HealthService`` (see #1) and ``SessionService``
(see #2), the in-memory ``SessionStore`` foundation that owns the live
``LLMAgent`` + ``SupervisedTaskHandler`` per session, the per-session
busy lock, and the server-authoritative ``need`` state machine. Actual
session creation (constructing an ``LLMAgent`` and calling
``run_supervised()``) is wired up by issue #3. The next-step /
run-step / approve-reject-abort orchestration that drives the
``need`` machine is wired up by issues #4-#6, #11-#14;
``SessionService.get_next_step`` (see #4) is the first of these.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from llm_agents_from_scratch import LLMAgent
from llm_agents_from_scratch.data_structures import (
    NextStepDecision,
    RejectedTaskResult,
    TaskResult,
    TaskStep,
    TaskStepResult,
)

Need = Literal["next", "run", "approve", "done"]
"""The server-authoritative state a session is waiting in.

Per the TRD §7 state machine:
    [*] -> next (create session)
    next -> run (next-step returns TaskStep)
    next -> approve (next-step returns TaskResult)
    run -> next (run-step returns TaskStepResult)
    approve -> done (complete())
    approve -> next (reject(feedback))
    next -> done (abort())
    run -> done (abort())
"""

_NEED_TRANSITIONS: dict[Need, frozenset[Need]] = {
    "next": frozenset({"run", "approve", "done"}),
    "run": frozenset({"next", "done"}),
    "approve": frozenset({"done", "next"}),
    "done": frozenset(),
}

_SESSION_ID_PREFIX = "sess_"
_SESSION_ID_TOKEN_BYTES = 8


class HealthService:
    """Reports whether the backend process is up and responsive."""

    def check(self) -> dict[str, str]:
        """Return the current liveness status of the backend.

        Returns:
            dict[str, str]: A status payload, e.g. ``{"status": "ok"}``.
        """
        return {"status": "ok"}


class SessionServiceError(Exception):
    """Base class for all ``SessionService`` domain exceptions.

    Framework-agnostic by design: ``services.py`` must not import
    FastAPI, so it is the route layer's job to catch these and
    translate them into ``HTTPException``s.
    """


class SessionNotFoundError(SessionServiceError):
    """Raised when a ``session_id`` has no corresponding live session.

    Route layer should map this to ``404``.
    """

    def __init__(self, session_id: str) -> None:
        """Initialize a SessionNotFoundError.

        Args:
            session_id (str): The unknown session identifier.
        """
        self.session_id = session_id
        super().__init__(f"No session found with id {session_id!r}.")


class SessionBusyError(SessionServiceError):
    """Raised when a session already has a mutating call in flight.

    Route layer should map this to ``409``.
    """

    def __init__(self, session_id: str) -> None:
        """Initialize a SessionBusyError.

        Args:
            session_id (str): The busy session's identifier.
        """
        self.session_id = session_id
        super().__init__(
            f"Session {session_id!r} already has a call in flight.",
        )


class WrongNeedError(SessionServiceError):
    """Raised when a call doesn't match the session's current ``need``.

    Route layer should map this to ``409``.
    """

    def __init__(self, session_id: str, expected: Need, actual: Need) -> None:
        """Initialize a WrongNeedError.

        Args:
            session_id (str): The affected session's identifier.
            expected (Need): The ``need`` the caller assumed.
            actual (Need): The session's actual current ``need``.
        """
        self.session_id = session_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Session {session_id!r} expected need {expected!r}, but is "
            f"currently at {actual!r}.",
        )


class InvalidNeedTransitionError(SessionServiceError):
    """Raised when a ``need`` transition isn't allowed by the TRD §7 FSM.

    This indicates a bug in the calling route/orchestration code (an
    illegal transition was attempted), not bad client input. Route
    layer should map this to ``409`` (or treat as a ``500``) rather
    than silently allowing it.
    """

    def __init__(self, session_id: str, current: Need, target: Need) -> None:
        """Initialize an InvalidNeedTransitionError.

        Args:
            session_id (str): The affected session's identifier.
            current (Need): The session's current ``need``.
            target (Need): The disallowed target ``need``.
        """
        self.session_id = session_id
        self.current = current
        self.target = target
        super().__init__(
            f"Session {session_id!r} cannot transition from "
            f"{current!r} to {target!r}.",
        )


@dataclass
class Session:
    """In-memory state for a single supervised-run session.

    Attributes:
        id (str): Opaque session identifier (``sess_`` + random token).
        agent (LLMAgent): The live ``LLMAgent`` driving this session.
        handler (Any): The live ``SupervisedTaskHandler`` for this
            session. Typed ``Any`` rather than imported from the
            framework because the pinned ``llm-agents-from-scratch``
            release this package depends on predates the
            ``SupervisedTaskHandler``/``run_supervised()`` API (added
            upstream but not yet released); once that lands, callers
            can rely on it exposing ``get_next_step``, ``run_step``,
            ``complete``, ``reject``, and ``abort``.
        need (Need): The server-authoritative state the session is
            waiting in. Defaults to ``"next"``.
        last_step_result (TaskStepResult | RejectedTaskResult | None):
            The value to pass as ``previous_step_result`` on the next
            ``handler.get_next_step()`` call (see #4). The framework's
            ``SupervisedTaskHandler`` is caller-driven and does not
            retain this between calls itself, so it has to live here.
            ``None`` until the first ``run_step()``/``reject()``
            completes, which is also what makes the framework treat
            the very first ``get_next_step()`` call as the
            deterministic "wrap the task instruction, no LLM call"
            case -- no separate first-call bookkeeping is needed.
            Set by issue #5 (``run_step``) and #6 (``reject``); read
            (never mutated) by issue #4 (``get_next_step``).
    """

    id: str
    agent: LLMAgent
    handler: Any
    need: Need = "next"
    last_step_result: TaskStepResult | RejectedTaskResult | None = None
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        repr=False,
        compare=False,
    )
    _busy: bool = field(default=False, repr=False, compare=False)


@dataclass(frozen=True)
class NextStepDecisionOutcome:
    """The "next_step" outcome of ``SessionService.get_next_step`` (#4).

    Attributes:
        decision (NextStepDecision): Mirrors the routing decision that
            produced ``step``. The framework's
            ``SupervisedTaskHandler.get_next_step`` doesn't hand back
            the ``NextStepDecision`` it (may have) obtained from the
            LLM -- it's consumed internally to build the returned
            ``TaskStep`` -- so this is reconstructed here rather than
            passed through. It's exact, not approximate: the
            framework sets ``TaskStep.instruction`` to the decision's
            ``content`` verbatim for the "next_step" kind, and the
            deterministic first-call path (no LLM consulted) has no
            real decision to reconstruct from in the first place, so
            the same construction is correct for both cases.
        step (TaskStep): The next step for the caller to run via
            run-step (#5).
        need (Need): The session's new ``need`` ("run").
    """

    decision: NextStepDecision
    step: TaskStep
    need: Need
    kind: Literal["next_step"] = "next_step"


@dataclass(frozen=True)
class NextStepFinalOutcome:
    """The "final_result" outcome of ``SessionService.get_next_step`` (#4).

    Attributes:
        result (TaskResult): The task's final result, awaiting
            operator approval/rejection (#6).
        need (Need): The session's new ``need`` ("approve").
    """

    result: TaskResult
    need: Need
    kind: Literal["final_result"] = "final_result"


NextStepOutcome = NextStepDecisionOutcome | NextStepFinalOutcome


class SessionService:
    """Owns the in-memory ``SessionStore`` and session lifecycle.

    Plain business logic: no FastAPI/Starlette imports. Routes reach
    this through the ``SessionServiceDep`` provider in ``deps.py`` and
    translate the exceptions raised here into HTTP responses.

    A single instance is shared for the process lifetime (see
    ``deps.get_session_service``) since it holds live in-memory
    session state that must not be recreated per request.
    """

    def __init__(self) -> None:
        """Initialize an empty SessionService."""
        self._sessions: dict[str, Session] = {}
        self._registry_lock = threading.Lock()

    @staticmethod
    def _generate_session_id() -> str:
        """Generate an opaque, unguessable session identifier.

        Returns:
            str: A new identifier of the form ``sess_<token>``.
        """
        token = secrets.token_urlsafe(_SESSION_ID_TOKEN_BYTES)
        return f"{_SESSION_ID_PREFIX}{token}"

    def create_session(self, agent: LLMAgent, handler: Any) -> Session:
        """Register a new session around an already-constructed handler.

        Actually constructing the ``LLMAgent`` and calling
        ``run_supervised()`` to obtain ``handler`` is issue #3's
        responsibility; this method only takes ownership of the
        result and starts it at ``need="next"``.

        Args:
            agent (LLMAgent): The live LLM agent for this session.
            handler (Any): The live ``SupervisedTaskHandler`` (or
                equivalent) for this session.

        Returns:
            Session: The newly created, stored session.
        """
        session = Session(
            id=self._generate_session_id(),
            agent=agent,
            handler=handler,
        )
        with self._registry_lock:
            self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session:
        """Look up a session by id.

        Args:
            session_id (str): The session identifier.

        Returns:
            Session: The matching session.

        Raises:
            SessionNotFoundError: If no session with that id exists.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def drop_session(self, session_id: str) -> None:
        """Remove a session, discarding its handler and agent.

        Args:
            session_id (str): The session identifier.

        Raises:
            SessionNotFoundError: If no session with that id exists.
        """
        with self._registry_lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(session_id)
            del self._sessions[session_id]

    def require_need(self, session: Session, expected: Need) -> None:
        """Assert a session is currently waiting on ``expected``.

        Later issues' routes call this at the top of each mutating
        endpoint (e.g. ``run-step`` requires ``need == "run"``) before
        touching the framework handler.

        Args:
            session (Session): The session to check.
            expected (Need): The ``need`` the caller requires.

        Raises:
            WrongNeedError: If ``session.need != expected``.
        """
        if session.need != expected:
            raise WrongNeedError(session.id, expected, session.need)

    def transition_need(self, session: Session, target: Need) -> None:
        """Move a session's ``need`` forward per the TRD §7 FSM.

        Args:
            session (Session): The session to transition.
            target (Need): The ``need`` to transition to.

        Raises:
            InvalidNeedTransitionError: If ``target`` is not reachable
                from the session's current ``need``.
        """
        allowed = _NEED_TRANSITIONS[session.need]
        if target not in allowed:
            raise InvalidNeedTransitionError(session.id, session.need, target)
        session.need = target

    @contextmanager
    def lock_session(self, session_id: str) -> Iterator[Session]:
        """Acquire the per-session busy flag for a mutating call.

        Non-blocking: if another call is already in flight for this
        session, raises immediately rather than queueing, so
        overlapping mutating calls (e.g. two concurrent ``run-step``
        requests) surface as ``409`` rather than serializing silently.

        Args:
            session_id (str): The session identifier.

        Yields:
            Session: The locked session, safe to mutate for the
                duration of the ``with`` block.

        Raises:
            SessionNotFoundError: If no session with that id exists.
            SessionBusyError: If the session already has a call in
                flight.
        """
        session = self.get_session(session_id)
        with self._registry_lock:
            if session._busy:
                raise SessionBusyError(session_id)
            session._busy = True
        try:
            yield session
        finally:
            with self._registry_lock:
                session._busy = False

    async def get_next_step(self, session_id: str) -> NextStepOutcome:
        """Advance a session through TRD §6.2's next-step transition.

        Calls ``session.handler.get_next_step()`` with
        ``session.last_step_result`` as ``previous_step_result`` --
        ``None`` on a session's first call, which the framework's own
        ``SupervisedTaskHandler.get_next_step`` already treats as
        "deterministically wrap the task instruction, no LLM call"
        (see ``Session.last_step_result`` for why no separate
        first-call tracking is needed here). On any later call,
        ``last_step_result`` holds whatever run-step (#5) or reject
        (#6) last stored, and the framework consults the LLM to route
        between another step and a final result.

        This method only reads ``last_step_result``; it's never
        mutated here.

        Args:
            session_id (str): The session identifier.

        Returns:
            NextStepOutcome: A ``NextStepDecisionOutcome`` when the
                handler produced another ``TaskStep`` (``need`` moves
                to ``"run"``), or a ``NextStepFinalOutcome`` when it
                produced a ``TaskResult`` (``need`` moves to
                ``"approve"``).

        Raises:
            SessionNotFoundError: If no session with that id exists.
            SessionBusyError: If the session already has a call in
                flight.
            WrongNeedError: If ``session.need != "next"``.
        """
        with self.lock_session(session_id) as session:
            self.require_need(session, "next")
            handler_result = await session.handler.get_next_step(
                session.last_step_result,
            )

            if isinstance(handler_result, TaskStep):
                self.transition_need(session, "run")
                return NextStepDecisionOutcome(
                    decision=NextStepDecision(
                        kind="next_step",
                        content=handler_result.instruction,
                    ),
                    step=handler_result,
                    need=session.need,
                )

            self.transition_need(session, "approve")
            return NextStepFinalOutcome(
                result=handler_result,
                need=session.need,
            )
