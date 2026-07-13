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
``LLMAgent`` and calls ``run_supervised()``. ``SessionService.
get_next_step`` (see #4), ``run_step`` (see #5), and ``complete`` (see
#6) drive the ``need`` machine the rest of the way; ``reject``/
``abort`` are wired up by later issues (#11-#14).
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from llm_agents_from_scratch import LLMAgent
from llm_agents_from_scratch.base.tool import AsyncBaseTool, BaseTool
from llm_agents_from_scratch.data_structures import (
    NextStepDecision,
    RejectedTaskResult,
    Task,
    TaskResult,
    TaskStep,
    TaskStepResult,
    ToolCall,
    ToolCallResult,
)
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


class NoPendingStepError(SessionServiceError):
    """Raised when ``run_step`` is called but no ``TaskStep`` is pending.

    This indicates a server-side invariant violation: ``need == "run"``
    is only ever set alongside a recorded ``pending_step`` (by the
    next-step endpoint, issue #4). Route layer should map this to
    ``500``.
    """

    def __init__(self, session_id: str) -> None:
        """Initialize a NoPendingStepError.

        Args:
            session_id (str): The affected session's identifier.
        """
        self.session_id = session_id
        super().__init__(
            f"Session {session_id!r} has need='run' but no pending "
            "TaskStep is recorded.",
        )


class MissingPendingResultError(SessionServiceError):
    """Raised when a session is at ``need="approve"`` with no pending result.

    ``require_need(session, "approve")`` guarantees the ``need`` is
    correct, but not that ``session.pending_result`` was actually
    populated; if it's missing here that's a bug in whatever
    transitioned the session into ``"approve"`` (``get_next_step``, #4),
    not a client error. Route layer should map this to ``500``.
    """

    def __init__(self, session_id: str) -> None:
        """Initialize a MissingPendingResultError.

        Args:
            session_id (str): The affected session's identifier.
        """
        self.session_id = session_id
        super().__init__(
            f"Session {session_id!r} is at need='approve' but has no "
            "pending_result stored.",
        )


class StepExecutionError(SessionServiceError):
    """Raised when the framework raises while executing a step.

    Wraps whatever exception ``SupervisedTaskHandler.run_step()``
    propagates (e.g. an LLM/network failure of the backbone LLM).
    Failed *tool calls* do not raise -- the framework already reports
    those as a ``ToolCallResult(error=True, ...)`` -- so this is
    reserved for LLM/framework-level failures. Route layer should map
    this to ``502``.
    """

    def __init__(self, session_id: str, cause: Exception) -> None:
        """Initialize a StepExecutionError.

        Args:
            session_id (str): The affected session's identifier.
            cause (Exception): The underlying exception raised by the
                framework.
        """
        self.session_id = session_id
        super().__init__(
            f"Session {session_id!r} failed to execute its pending "
            f"step: {cause}",
        )


@dataclass
class ToolCallTrace:
    """A single tool call executed as part of a ``run_step`` call.

    Attributes:
        tool_name (str): Name of the tool that was called.
        args (dict[str, Any]): Arguments the LLM supplied for the call.
        content (Any): The tool's result content.
        error (bool): Whether the tool call itself errored.
    """

    tool_name: str
    args: dict[str, Any]
    content: Any
    error: bool


@dataclass
class RunStepOutcome:
    """The outcome of executing a session's pending ``TaskStep``.

    Attributes:
        result (TaskStepResult): The framework's step result.
        tool_calls (list[ToolCallTrace]): Trace of every tool call made
            while executing the step, in call order.
        step_counter (int): The handler's running count of executed
            steps (the framework's own ``TaskHandler.step_counter``,
            which starts at ``0`` and is incremented at the start of
            each ``run_step()`` call -- so after the Nth successful
            run-step call this equals ``N``).
        need (Need): The session's ``need`` after this call (``"next"``
            on success).
    """

    result: TaskStepResult
    tool_calls: list[ToolCallTrace]
    step_counter: int
    need: Need


class _RecordingSyncTool(BaseTool):
    """Wraps a synchronous ``Tool``, recording each call to a recorder."""

    def __init__(self, wrapped: BaseTool, recorder: _ToolCallRecorder) -> None:
        """Initialize a _RecordingSyncTool.

        Args:
            wrapped (BaseTool): The real tool to delegate execution to.
            recorder (_ToolCallRecorder): Collects a trace of calls.
        """
        self._wrapped = wrapped
        self._recorder = recorder

    @property
    def name(self) -> str:
        """Name of the wrapped tool."""
        return self._wrapped.name

    @property
    def description(self) -> str:
        """Description of the wrapped tool."""
        return self._wrapped.description

    @property
    def parameters_json_schema(self) -> dict[str, Any]:
        """JSON schema of the wrapped tool."""
        return self._wrapped.parameters_json_schema

    def __call__(
        self,
        tool_call: ToolCall,
        *args: Any,
        **kwargs: Any,
    ) -> ToolCallResult:
        """Execute the wrapped tool and record the call."""
        result = self._wrapped(tool_call, *args, **kwargs)
        self._recorder.record(tool_call, result)
        return result


class _RecordingAsyncTool(AsyncBaseTool):
    """Wraps an asynchronous ``Tool``, recording each call to a recorder."""

    def __init__(
        self,
        wrapped: AsyncBaseTool,
        recorder: _ToolCallRecorder,
    ) -> None:
        """Initialize a _RecordingAsyncTool.

        Args:
            wrapped (AsyncBaseTool): The real tool to delegate to.
            recorder (_ToolCallRecorder): Collects a trace of calls.
        """
        self._wrapped = wrapped
        self._recorder = recorder

    @property
    def name(self) -> str:
        """Name of the wrapped tool."""
        return self._wrapped.name

    @property
    def description(self) -> str:
        """Description of the wrapped tool."""
        return self._wrapped.description

    @property
    def parameters_json_schema(self) -> dict[str, Any]:
        """JSON schema of the wrapped tool."""
        return self._wrapped.parameters_json_schema

    async def __call__(
        self,
        tool_call: ToolCall,
        *args: Any,
        **kwargs: Any,
    ) -> ToolCallResult:
        """Execute the wrapped tool and record the call."""
        result = await self._wrapped(tool_call, *args, **kwargs)
        self._recorder.record(tool_call, result)
        return result


class _ToolCallRecorder:
    """Accumulates a ``ToolCallTrace`` per real tool execution."""

    def __init__(self) -> None:
        """Initialize an empty recorder."""
        self.traces: list[ToolCallTrace] = []

    def record(self, tool_call: ToolCall, result: ToolCallResult) -> None:
        """Append a trace entry for one executed tool call.

        Args:
            tool_call (ToolCall): The call the LLM requested.
            result (ToolCallResult): The result of executing it.
        """
        self.traces.append(
            ToolCallTrace(
                tool_name=tool_call.tool_name,
                args=tool_call.arguments,
                content=result.content,
                error=result.error,
            ),
        )


def _wrap_tool_for_recording(
    tool: BaseTool | AsyncBaseTool,
    recorder: _ToolCallRecorder,
) -> BaseTool | AsyncBaseTool:
    """Wrap a tool so its real execution is recorded by ``recorder``.

    Preserves whether the tool is sync (``BaseTool``) or async
    (``AsyncBaseTool``): ``TaskHandler.run_step`` branches on
    ``isinstance(tool, AsyncBaseTool)`` to decide whether to ``await``
    it, so the wrapper must match the wrapped tool's kind.

    Args:
        tool (BaseTool | AsyncBaseTool): The real, registered tool.
        recorder (_ToolCallRecorder): Collects a trace of calls.

    Returns:
        BaseTool | AsyncBaseTool: A same-kind wrapper that delegates
            to ``tool`` and records the call.
    """
    if isinstance(tool, AsyncBaseTool):
        return _RecordingAsyncTool(tool, recorder)
    return _RecordingSyncTool(tool, recorder)


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
        pending_step (TaskStep | None): The ``TaskStep`` currently
            awaiting execution via ``run_step`` (see #5). Set by
            ``get_next_step`` (#4) whenever it transitions ``need`` to
            ``"run"``; consumed and cleared by ``run_step`` (#5).
            ``None`` whenever ``need != "run"``.
        pending_result (TaskResult | None): The proposed ``TaskResult``
            awaiting operator approval. Set by ``get_next_step`` (#4)
            whenever it transitions ``need`` to ``"approve"``; consumed
            and cleared by ``complete`` (#6) or (later) ``reject``
            (#11).
        last_step_result (TaskStepResult | RejectedTaskResult | None):
            The value to pass as ``previous_step_result`` on the next
            ``handler.get_next_step()`` call (see #4). The framework's
            ``SupervisedTaskHandler`` is caller-driven and does not
            retain this between calls itself, so it has to live here.
            ``None`` until the first ``run_step()``/``reject()``
            completes, which is also what makes the framework treat
            the very first ``get_next_step()`` call as the
            deterministic "wrap the task instruction, no LLM call"
            case -- no separate first-call bookkeeping is needed. Set
            by ``run_step`` (#5) and (later) ``reject`` (#11); read
            (never mutated) by ``get_next_step`` (#4).
    """

    id: str
    agent: LLMAgent
    handler: Any
    need: Need = "next"
    pending_step: TaskStep | None = None
    pending_result: TaskResult | None = None
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
        (#11) last stored, and the framework consults the LLM to route
        between another step and a final result.

        This method only reads ``last_step_result``; it's never
        mutated here. It *writes* ``session.pending_step`` (for
        run-step, #5, to consume) when the outcome is another step, or
        ``session.pending_result`` (for complete, #6, to consume) when
        the outcome is a final result.

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
                session.pending_step = handler_result
                self.transition_need(session, "run")
                return NextStepDecisionOutcome(
                    decision=NextStepDecision(
                        kind="next_step",
                        content=handler_result.instruction,
                    ),
                    step=handler_result,
                    need=session.need,
                )

            session.pending_result = handler_result
            self.transition_need(session, "approve")
            return NextStepFinalOutcome(
                result=handler_result,
                need=session.need,
            )

    async def run_step(self, session: Session) -> RunStepOutcome:
        """Execute a session's pending ``TaskStep`` (see #5).

        Calls the framework's ``SupervisedTaskHandler.run_step(step)``
        on ``session.pending_step``. Real tools registered on
        ``session.agent`` (e.g. ``next_number``) execute for real as
        part of the framework's own tool-calling loop inside
        ``run_step`` -- this method only wraps each registered tool
        for the duration of the call so it can build a ``tool_calls[]``
        trace; it does not stub or intercept execution. On success,
        clears ``pending_step``, stores the result as
        ``session.last_step_result`` (for the next ``get_next_step``
        call, #4, to consume), and transitions ``need`` back to
        ``"next"``.

        Callers should hold the session's busy lock (``lock_session``)
        for the duration of this call.

        Args:
            session (Session): The session to advance. Must have
                ``need == "run"``.

        Returns:
            RunStepOutcome: The step result, tool-call trace, updated
                step counter, and resulting ``need``.

        Raises:
            WrongNeedError: If ``session.need != "run"``.
            NoPendingStepError: If ``need == "run"`` but no
                ``pending_step`` is recorded (server invariant bug).
            StepExecutionError: If the framework raises while running
                the step (LLM/framework-level failure, not a failed
                tool call -- those are reported in the trace instead).
        """
        self.require_need(session, "run")
        step = session.pending_step
        if step is None:
            raise NoPendingStepError(session.id)

        recorder = _ToolCallRecorder()
        original_tools = dict(session.agent.tools_registry)
        for tool_name, tool in original_tools.items():
            session.agent.tools_registry[tool_name] = _wrap_tool_for_recording(
                tool,
                recorder,
            )
        try:
            result = await session.handler.run_step(step)
        except Exception as e:
            raise StepExecutionError(session.id, e) from e
        finally:
            session.agent.tools_registry.clear()
            session.agent.tools_registry.update(original_tools)

        session.pending_step = None
        session.last_step_result = result
        self.transition_need(session, "next")

        return RunStepOutcome(
            result=result,
            tool_calls=recorder.traces,
            step_counter=getattr(session.handler, "step_counter", 0),
            need=session.need,
        )

    async def complete(self, session: Session) -> TaskResult:
        """Approve the session's pending ``TaskResult`` and resolve it.

        Per TRD §6.4 (see #6): requires ``session.need == "approve"``;
        calls the framework's ``SupervisedTaskHandler.complete(result)``,
        which records the episode to memory and resolves the handler
        (an ``asyncio.Future``) with ``result``. Then clears the
        session's pending result and transitions ``need`` to ``"done"``.

        Args:
            session (Session): The session to complete. Callers should
                obtain this via ``lock_session()`` so the mutation is
                serialized against other calls on the same session.

        Returns:
            TaskResult: The now-approved task result.

        Raises:
            WrongNeedError: If ``session.need != "approve"``.
            MissingPendingResultError: If ``session.need == "approve"``
                but ``session.pending_result`` is unset (indicates a
                bug upstream, not a client error).
        """
        self.require_need(session, "approve")
        result = session.pending_result
        if result is None:
            raise MissingPendingResultError(session.id)

        await session.handler.complete(result)

        session.pending_result = None
        self.transition_need(session, "done")
        return result
