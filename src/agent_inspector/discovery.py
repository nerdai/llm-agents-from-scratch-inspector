"""Convention-based entrypoint discovery (see ADR-002, issue #47).

Agent Inspector no longer builds an ``LLMAgent`` from an HTTP request
body (M1). Instead, a user authors a Python script that constructs an
``LLMAgentBuilder`` (the framework's own recommended pattern -- real
tools, skills, memories, and a model, all in code via its fluent
``with_*`` methods) and exposes it at a well-known module-level name.
``agent-inspector launch <script>`` imports that script the same way
Gradio discovers a user's ``demo`` object: standard ``importlib``
machinery against an arbitrary file path, then a lookup of a
conventionally-named attribute -- not a subprocess, not a wire
protocol.

This module owns that import + discovery mechanism and is the single
place that turns every way it can fail (missing script, broken import,
missing attribute, wrong type, builder with no ``llm`` configured)
into a clear, actionable ``EntrypointDiscoveryError`` -- so ``cli.py``
can catch one exception type and print a message instead of letting a
raw traceback (or, worse, an opaque failure on the first
``POST /sessions``) reach the user. This is deliberately a startup-time
concern, not per-request business logic, so it lives here rather than
in ``services/session.py`` (see the FastAPI layering standard in
``docs/overview.md``).
"""

import importlib.util
import sys
from pathlib import Path

from llm_agents_from_scratch import LLMAgentBuilder

AGENT_BUILDER_ATTR = "agent_builder"
"""The well-known module-level name Agent Inspector looks for in a
user's entrypoint script.

Documented here as the single source of truth; also surfaced in
``agent-inspector launch --help`` and ``docs/overview.md``.
"""


class EntrypointDiscoveryError(Exception):
    """Base class for every way entrypoint discovery can fail.

    ``cli.py`` catches this single type (not the more specific
    subclasses below) at ``launch`` time and prints ``str(e)`` instead
    of letting a raw traceback reach the user.
    """


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


def discover_agent_builder(script_path: Path) -> LLMAgentBuilder:
    """Import ``script_path`` and discover its ``LLMAgentBuilder``.

    Uses ``importlib.util.spec_from_file_location`` +
    ``module_from_spec`` -- the standard mechanism for importing an
    arbitrary file path that isn't necessarily on ``sys.path`` or part
    of an installed package -- then looks up ``AGENT_BUILDER_ATTR`` on
    the resulting module.

    Args:
        script_path (Path): Path to the user's entrypoint script.

    Returns:
        LLMAgentBuilder: The discovered builder, verified to have
            ``llm`` already configured.

    Raises:
        ScriptNotFoundError: If ``script_path`` doesn't exist.
        ScriptImportError: If the script raises while being imported.
        MissingAgentBuilderError: If the script has no
            ``AGENT_BUILDER_ATTR`` attribute.
        InvalidAgentBuilderTypeError: If that attribute isn't an
            ``LLMAgentBuilder`` instance.
        AgentBuilderNotReadyError: If the builder has no ``llm`` set.
    """
    if not script_path.is_file():
        raise ScriptNotFoundError(script_path)

    module_name = f"_agent_inspector_entrypoint_{script_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ScriptImportError(
            script_path,
            ImportError(f"could not build an import spec for {script_path}"),
        )

    module = importlib.util.module_from_spec(spec)
    # Registering the module under sys.modules before exec_module
    # mirrors what a normal `import` does, so the script's own
    # relative imports/dataclasses/etc. behave the same as they would
    # if the user ran it directly with `python main.py`.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as e:
        sys.modules.pop(module_name, None)
        raise ScriptImportError(script_path, e) from e

    if not hasattr(module, AGENT_BUILDER_ATTR):
        raise MissingAgentBuilderError(script_path)

    agent_builder = getattr(module, AGENT_BUILDER_ATTR)
    if not isinstance(agent_builder, LLMAgentBuilder):
        raise InvalidAgentBuilderTypeError(script_path, agent_builder)

    if agent_builder.llm is None:
        raise AgentBuilderNotReadyError(script_path)

    return agent_builder
