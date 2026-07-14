"""Domain exceptions raised by ``services/session.py``.

Framework-agnostic by design: nothing in ``services/`` may import
FastAPI, so these are plain ``Exception`` subclasses. It's the route
layer's job (``routes/``) to catch them and translate them into
``HTTPException``s -- each docstring below notes the status code that
mapping should use.

Deliberately has no dependency on ``services/`` (the ``expected``/
``actual``/``current`` params below take a plain ``str`` rather than
``services.session.Need``): errors sits *below* services in the
dependency graph, so importing ``Need`` from there would make it
circular.
"""


class SessionServiceError(Exception):
    """Base class for all ``SessionService`` domain exceptions."""


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

    def __init__(self, session_id: str, expected: str, actual: str) -> None:
        """Initialize a WrongNeedError.

        Args:
            session_id (str): The affected session's identifier.
            expected (str): The ``need`` the caller assumed.
            actual (str): The session's actual current ``need``.
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

    def __init__(self, session_id: str, current: str, target: str) -> None:
        """Initialize an InvalidNeedTransitionError.

        Args:
            session_id (str): The affected session's identifier.
            current (str): The session's current ``need``.
            target (str): The disallowed target ``need``.
        """
        self.session_id = session_id
        self.current = current
        self.target = target
        super().__init__(
            f"Session {session_id!r} cannot transition from "
            f"{current!r} to {target!r}.",
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


class NoEditableResultError(SessionServiceError):
    """Raised when ``edit_result`` is called with nothing editable.

    ``need == "next"`` (checked separately via ``require_need``) is
    necessary but not sufficient for editing: it's also the ``need``
    right after session creation (before any ``run_step``) and right
    after a rejection (see ``reject``, #11), and in neither case does
    ``session.last_step_result`` hold a ``TaskStepResult`` with a
    corresponding ``rollout`` span to splice into. Route layer should
    map this to ``409`` -- it's a legitimate, client-reachable session
    state, not a server bug.
    """

    def __init__(self, session_id: str) -> None:
        """Initialize a NoEditableResultError.

        Args:
            session_id (str): The affected session's identifier.
        """
        self.session_id = session_id
        super().__init__(
            f"Session {session_id!r} has no TaskStepResult available to "
            "edit right now.",
        )


class MissingRolloutSpanError(SessionServiceError):
    """Raised when a ``TaskStepResult`` is editable but has no rollout span.

    ``run_step`` (#5) always records ``last_rollout_span`` alongside
    ``last_step_result`` when it stores a ``TaskStepResult``, so this
    indicates a server-side invariant violation, not a client error.
    Route layer should map this to ``500``.
    """

    def __init__(self, session_id: str) -> None:
        """Initialize a MissingRolloutSpanError.

        Args:
            session_id (str): The affected session's identifier.
        """
        self.session_id = session_id
        super().__init__(
            f"Session {session_id!r} has an editable TaskStepResult but "
            "no last_rollout_span is recorded.",
        )


class AgentBuilderNotConfiguredError(SessionServiceError):
    """Raised when no ``LLMAgentBuilder`` is wired into the SessionService.

    Indicates the process wasn't launched via ``agent-inspector launch
    <script>`` (which discovers and configures a builder -- see
    ``discovery.py`` -- before the app starts serving requests). A
    server misconfiguration, not a client error. Route layer should
    map this to ``500``.
    """

    def __init__(self) -> None:
        """Initialize an AgentBuilderNotConfiguredError."""
        super().__init__(
            "No LLMAgentBuilder is configured on this SessionService. "
            "Launch via `agent-inspector launch <script>` so one is "
            "discovered and wired up before sessions can be created.",
        )


class AgentBuildError(SessionServiceError):
    """Raised when the configured ``LLMAgentBuilder`` fails to build.

    Wraps whatever ``LLMAgentBuilder.build()`` raises -- e.g. an
    ``LLMAgentBuilderError`` (shouldn't happen here in practice, since
    ``agent-inspector launch`` already validates ``llm`` is set before
    serving any requests -- see ``discovery.py``) or a transient
    failure discovering MCP tools. Route layer should map this to
    ``502``.
    """

    def __init__(self, cause: Exception) -> None:
        """Initialize an AgentBuildError.

        Args:
            cause (Exception): The underlying exception the builder's
                ``build()`` raised.
        """
        self.cause = cause
        super().__init__(
            f"Failed to build agent from configured builder: {cause}",
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
