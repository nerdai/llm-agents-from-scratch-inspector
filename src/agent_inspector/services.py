"""Business-logic services for Agent Inspector.

This module is the only place domain/business logic lives. Routes
(``routes.py``) call into services through the dependency-injected
instances declared in ``deps.py``; services raise domain exceptions
rather than ``fastapi.HTTPException``, leaving HTTP-status mapping to
the route layer.

This module contains ``HealthService`` (see #1) and ``SessionService``
(see #2), the in-memory ``SessionStore`` foundation that owns the live
``LLMAgent`` + ``SupervisedTaskHandler`` per session, the per-session
busy lock, and the server-authoritative ``need`` state machine.
``SessionService.create_session_from_config()`` (see #3) builds the
``LLMAgent`` and calls ``run_supervised()``; the step/approve/reject/
abort orchestration that drives the ``need`` machine the rest of the
way is wired up by later issues (#4-#6, #11-#14).
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from llm_agents_from_scratch import LLMAgent
from llm_agents_from_scratch.data_structures import Task
from llm_agents_from_scratch.llms import OllamaLLM
from llm_agents_from_scratch.tools import SimpleFunctionTool

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

# M1 (issue #3) hardcodes exactly one real function tool, regardless of
# what a client's ``function_tools`` request field names -- genuine
# arbitrary function-tool registration is issue #8's (M2) job. This is
# the TRD's running Hailstone-sequence example.
NEXT_NUMBER_TOOL_NAME = "next_number"

# Framework defaults, matching the framework's own ch08 examples
# (`examples/ch08.ipynb`) and the TRD §6.1 request example.
DEFAULT_OLLAMA_MODEL = "qwen3:14b"
DEFAULT_THINK = False


def next_number(x: int) -> int:
    """Hailstone-sequence step function.

    M1's one hardcoded real function tool (see ``NEXT_NUMBER_TOOL_NAME``).

    Args:
        x (int): The current value in the sequence.

    Returns:
        int: ``x // 2`` if ``x`` is even, else ``3 * x + 1``.
    """
    return x // 2 if x % 2 == 0 else 3 * x + 1


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


class SessionConfigError(SessionServiceError):
    """Raised when the config for a new session is invalid.

    Route layer should map this to ``422``.
    """

    def __init__(self, message: str) -> None:
        """Initialize a SessionConfigError.

        Args:
            message (str): Human-readable description of what's wrong
                with the supplied config.
        """
        self.message = message
        super().__init__(message)


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
    """

    id: str
    agent: LLMAgent
    handler: Any
    need: Need = "next"
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        repr=False,
        compare=False,
    )
    _busy: bool = field(default=False, repr=False, compare=False)


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

    async def create_session_from_config(
        self,
        *,
        task: str,
        model: str | None = None,
        think: bool | None = None,
        function_tools: Sequence[str] | None = None,
    ) -> Session:
        """Build an ``LLMAgent``, start a supervised run, register it.

        Implements TRD §6.1 (issue #3): builds an ``LLMAgent`` wired to
        an ``OllamaLLM`` backbone and calls ``run_supervised(task)`` to
        obtain the ``SupervisedTaskHandler``, then hands the resulting
        agent/handler pair to ``create_session()``.

        M1 scope: only ``task``, ``model``, and ``think`` are actually
        acted on. ``function_tools`` is accepted but ignored -- the
        agent is always equipped with exactly one real tool,
        ``next_number`` (see ``NEXT_NUMBER_TOOL_NAME``); genuine
        arbitrary function-tool registration is issue #8 (M2).
        ``skills_scopes``/``explicit_only_skills``/``mcp_servers`` are
        M2/M3 scope and aren't parameters here -- the route layer
        accepts and ignores them for now.

        Args:
            task (str): The task instruction.
            model (str | None): Ollama model name. Defaults to
                ``DEFAULT_OLLAMA_MODEL`` if not provided.
            think (bool | None): Enable/disable Ollama thinking mode.
                Defaults to ``DEFAULT_THINK`` if not provided.
            function_tools (Sequence[str] | None): Names of function
                tools requested by the client. Accepted for forward
                compatibility but currently ignored -- see above.

        Returns:
            Session: The newly created, stored session, at
                ``need="next"``.

        Raises:
            SessionConfigError: If ``task`` is blank.
        """
        del function_tools  # M1: always registers next_number; see above.

        if not task or not task.strip():
            raise SessionConfigError("`task` must be a non-empty string.")

        llm = OllamaLLM(
            model=model or DEFAULT_OLLAMA_MODEL,
            think=think if think is not None else DEFAULT_THINK,
        )
        agent = LLMAgent(llm=llm, tools=[SimpleFunctionTool(func=next_number)])
        handler = await agent.run_supervised(Task(instruction=task))
        return self.create_session(agent, handler)

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
