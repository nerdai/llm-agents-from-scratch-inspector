"""Exceptions raised by ``discovery.py`` (entrypoint discovery, ADR-002).

``cli.py`` catches ``EntrypointDiscoveryError`` (not the more specific
subclasses below) at ``agent-inspector launch`` time and prints
``str(e)`` instead of letting a raw traceback reach the user. These
are a startup-time concern -- unlike ``errors/session.py``, they never
reach the route layer, so none of them carry an HTTP-status mapping.
"""

from pathlib import Path

AGENT_BUILDER_ATTR = "agent_builder"
"""The well-known module-level name Agent Inspector looks for in a
user's entrypoint script.

Documented here (rather than in ``discovery.py``) as the single source
of truth shared by both the discovery logic and its error messages;
also surfaced in ``agent-inspector launch --help`` and
``docs/overview.md``.
"""

DEFAULT_TASK_ATTR = "default_task"
"""The well-known, optional module-level name for a script's default
``Task``, shown pre-filled in the UI's task field at launch time
instead of a hardcoded string baked into the frontend. Unlike
``AGENT_BUILDER_ATTR``, absence is not an error -- a script with no
``default_task`` just leaves the field blank.
"""


class EntrypointDiscoveryError(Exception):
    """Base class for every way entrypoint discovery can fail."""


class ScriptNotFoundError(EntrypointDiscoveryError):
    """Raised when the given script path doesn't exist."""

    def __init__(self, path: Path) -> None:
        """Initialize a ScriptNotFoundError.

        Args:
            path (Path): The script path that doesn't exist.
        """
        self.path = path
        super().__init__(
            f"Agent script not found: {path}\n"
            "Pass the path to a Python script that defines a "
            f"module-level `{AGENT_BUILDER_ATTR}` (an LLMAgentBuilder "
            "instance), e.g. `agent-inspector launch main.py`.",
        )


class ScriptImportError(EntrypointDiscoveryError):
    """Raised when the script exists but raises while being imported.

    Wraps whatever the script itself raised (a ``SyntaxError``, an
    ``ImportError`` from one of its own imports, an exception raised
    at module scope, ...).
    """

    def __init__(self, path: Path, cause: BaseException) -> None:
        """Initialize a ScriptImportError.

        Args:
            path (Path): The script that failed to import.
            cause (BaseException): The exception it raised.
        """
        self.path = path
        self.cause = cause
        super().__init__(
            f"Failed to import agent script {path}:\n"
            f"  {type(cause).__name__}: {cause}",
        )


class MissingAgentBuilderError(EntrypointDiscoveryError):
    """Raised when the script has no ``AGENT_BUILDER_ATTR`` attribute."""

    def __init__(self, path: Path) -> None:
        """Initialize a MissingAgentBuilderError.

        Args:
            path (Path): The script missing the attribute.
        """
        self.path = path
        super().__init__(
            f"Agent script {path} does not define a module-level "
            f"`{AGENT_BUILDER_ATTR}`.\n"
            "Expose an LLMAgentBuilder instance under that name, e.g.:\n"
            f"    {AGENT_BUILDER_ATTR} = LLMAgentBuilder().with_llm(llm)",
        )


class InvalidAgentBuilderTypeError(EntrypointDiscoveryError):
    """Raised when ``AGENT_BUILDER_ATTR`` isn't an ``LLMAgentBuilder``."""

    def __init__(self, path: Path, actual: object) -> None:
        """Initialize an InvalidAgentBuilderTypeError.

        Args:
            path (Path): The script with the wrongly-typed attribute.
            actual (object): The value actually found.
        """
        self.path = path
        self.actual_type = type(actual)
        super().__init__(
            f"Agent script {path}'s `{AGENT_BUILDER_ATTR}` is a "
            f"{self.actual_type.__name__}, not an LLMAgentBuilder.",
        )


class InvalidDefaultTaskTypeError(EntrypointDiscoveryError):
    """Raised when ``DEFAULT_TASK_ATTR`` isn't a ``Task``."""

    def __init__(self, path: Path, actual: object) -> None:
        """Initialize an InvalidDefaultTaskTypeError.

        Args:
            path (Path): The script with the wrongly-typed attribute.
            actual (object): The value actually found.
        """
        self.path = path
        self.actual_type = type(actual)
        super().__init__(
            f"Agent script {path}'s `{DEFAULT_TASK_ATTR}` is a "
            f"{self.actual_type.__name__}, not a Task.",
        )


class AgentBuilderNotReadyError(EntrypointDiscoveryError):
    """Raised when the discovered builder has no ``llm`` configured.

    Mirrors ``LLMAgentBuilder.build()``'s own ``LLMAgentBuilderError``
    (which would otherwise only surface lazily, on the first
    ``POST /sessions``) but checked eagerly here so it fails at
    ``agent-inspector launch`` time instead (see ADR-002).
    """

    def __init__(self, path: Path) -> None:
        """Initialize an AgentBuilderNotReadyError.

        Args:
            path (Path): The script whose builder has no ``llm`` set.
        """
        self.path = path
        super().__init__(
            f"Agent script {path}'s `{AGENT_BUILDER_ATTR}` has no `llm` "
            "configured.\n"
            f"Call `.with_llm(...)` on it before `agent-inspector "
            "launch` can use it.",
        )
