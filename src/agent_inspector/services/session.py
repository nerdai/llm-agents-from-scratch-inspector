"""Session lifecycle business logic (see #2).

The in-memory ``SessionStore`` foundation that owns the live
``LLMAgent`` + ``SupervisedTaskHandler`` per session, the per-session
busy lock, and the server-authoritative ``need`` state machine.
``SessionService.create_session_from_config()`` (see #3, reworked by
#47/ADR-002) calls the configured ``LLMAgentBuilder.build()`` and
``run_supervised()``. ``SessionService.get_next_step`` (see #4),
``run_step`` (see #5), and ``complete`` (see #6) drive the ``need``
machine the rest of the way; ``reject``/``abort`` are wired up by
later issues (#11-#14).
"""

import asyncio
import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from llm_agents_from_scratch import LLMAgent, LLMAgentBuilder
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

from agent_inspector.errors.session import (
    AgentBuilderNotConfiguredError,
    AgentBuildError,
    InvalidNeedTransitionError,
    MissingPendingResultError,
    NoPendingStepError,
    SessionBusyError,
    SessionConfigError,
    SessionNotFoundError,
    StepExecutionError,
    WrongNeedError,
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
            session, as returned by ``LLMAgent.run_supervised()``.
            Typed ``Any`` rather than the real type because
            ``SupervisedTaskHandler`` is a nested class
            (``LLMAgent.SupervisedTaskHandler``) rather than a
            top-level, independently importable name; a ``Protocol``
            covering the ``get_next_step``/``run_step``/``complete``/
            ``reject``/``abort`` surface this code actually calls
            would be a cleaner fit than importing the nested type
            directly, but hasn't been introduced yet.
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

    def __init__(self, agent_builder: LLMAgentBuilder | None = None) -> None:
        """Initialize an empty SessionService.

        Args:
            agent_builder (LLMAgentBuilder | None, optional): The
                CLI-discovered builder (see ``discovery.py``) that
                ``create_session_from_config`` calls ``.build()`` on
                once per new session. ``None`` until ``deps.py``'s
                ``configure_agent_builder`` wires one up at CLI launch
                time -- left optional (rather than required) so tests
                that only exercise session lifecycle/need-machine
                behavior (never session *creation*) can keep
                constructing a bare ``SessionService()``.
        """
        self._sessions: dict[str, Session] = {}
        self._registry_lock = threading.Lock()
        self.agent_builder = agent_builder

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
        with self._registry_lock:
            session_id = self._generate_session_id()
            while session_id in self._sessions:
                session_id = self._generate_session_id()
            session = Session(id=session_id, agent=agent, handler=handler)
            self._sessions[session_id] = session
        return session

    async def create_session_from_config(self, *, task: str) -> Session:
        """Build an ``LLMAgent``, start a supervised run, register it.

        Implements TRD §6.1 (issue #3), reworked per ADR-002 (#47):
        rather than constructing an ``LLMAgent`` from HTTP config, this
        calls ``self.agent_builder.build()`` -- the ``LLMAgentBuilder``
        that ``agent-inspector launch <script>`` discovered from the
        user's own script (see ``discovery.py``) -- to obtain a fresh,
        independent ``LLMAgent`` for this session, then calls
        ``run_supervised(task)`` to obtain the ``SupervisedTaskHandler``
        and hands the resulting agent/handler pair to
        ``create_session()``.

        Every model/tools/skills/memory choice now lives in the
        discovered builder rather than the request body; ``task`` is
        the only thing that still varies per session (see ADR-002's
        rationale for why that's inherent to "drive one task at a
        time").

        Args:
            task (str): The task instruction.

        Returns:
            Session: The newly created, stored session, at
                ``need="next"``.

        Raises:
            SessionConfigError: If ``task`` is blank.
            AgentBuilderNotConfiguredError: If no ``agent_builder`` was
                wired up (the process wasn't launched via
                ``agent-inspector launch <script>``).
            AgentBuildError: If the configured builder's ``build()``
                raises.
        """
        if not task or not task.strip():
            raise SessionConfigError("`task` must be a non-empty string.")

        if self.agent_builder is None:
            raise AgentBuilderNotConfiguredError

        try:
            agent = await self.agent_builder.build()
        except asyncio.CancelledError:
            # Let cancellation (client disconnect, timeout) propagate
            # instead of being wrapped as a 502 -- this isn't a genuine
            # build failure.
            raise
        except Exception as e:
            raise AgentBuildError(e) from e

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
        with self._registry_lock:
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
            SessionBusyError: If the session has a mutating call
                currently in flight (held via ``lock_session``).
        """
        with self._registry_lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            if session._busy:
                raise SessionBusyError(session_id)
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
        with self._registry_lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
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
