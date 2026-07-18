"""Convention-based entrypoint discovery (see ADR-002, issue #47).

Agent Inspector no longer builds an ``LLMAgent`` from an HTTP request
body (M1). Instead, a user authors a Python script that constructs an
``LLMAgentBuilder`` (the framework's own recommended pattern -- real
tools, skills, memories, and a model, all in code via its fluent
``with_*`` methods) and exposes it at a well-known module-level name.
``agent-inspector launch <script>`` imports that script the same way
Gradio discovers a user's ``demo`` object: standard ``importlib``
machinery against an arbitrary file path, then a lookup of
conventionally-named attributes -- not a subprocess, not a wire
protocol. A script can also expose an optional module-level
``default_task`` (a ``Task``), shown pre-filled in the UI's task field
at launch time instead of a value hardcoded in the frontend.

This module owns that import + discovery mechanism. Every way it can
fail (missing script, broken import, missing attribute, wrong type,
builder with no ``llm`` configured) is a distinct exception in
``errors/discovery.py`` -- see that module for the full hierarchy and
messages -- so ``cli.py`` can catch one base type and print a message
instead of letting a raw traceback (or, worse, an opaque failure on
the first ``POST /sessions``) reach the user. This is deliberately a
startup-time concern, not per-request business logic, so it lives here
rather than in ``services/session.py`` (see the FastAPI layering
standard in ``docs/overview.md``).
"""

import importlib.util
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from llm_agents_from_scratch import LLMAgentBuilder
from llm_agents_from_scratch.data_structures import Task

from agent_inspector.errors.discovery import (
    AGENT_BUILDER_ATTR,
    DEFAULT_TASK_ATTR,
    AgentBuilderNotReadyError,
    InvalidAgentBuilderTypeError,
    InvalidDefaultTaskTypeError,
    MissingAgentBuilderError,
    ScriptImportError,
    ScriptNotFoundError,
)


@dataclass(frozen=True)
class DiscoveredEntrypoint:
    """Everything ``discover_entrypoint`` finds in a user's script."""

    agent_builder: LLMAgentBuilder
    default_task: Task | None


def discover_entrypoint(script_path: Path) -> DiscoveredEntrypoint:
    """Import ``script_path`` and discover its entrypoint.

    Uses ``importlib.util.spec_from_file_location`` +
    ``module_from_spec`` -- the standard mechanism for importing an
    arbitrary file path that isn't necessarily on ``sys.path`` or part
    of an installed package -- then looks up ``AGENT_BUILDER_ATTR``
    (required) and ``DEFAULT_TASK_ATTR`` (optional) on the resulting
    module.

    Args:
        script_path (Path): Path to the user's entrypoint script.

    Returns:
        DiscoveredEntrypoint: The discovered ``agent_builder``
            (verified to have ``llm`` already configured) and
            ``default_task`` (``None`` if the script doesn't define
            one).

    Raises:
        ScriptNotFoundError: If ``script_path`` doesn't exist.
        ScriptImportError: If the script raises while being imported.
        MissingAgentBuilderError: If the script has no
            ``AGENT_BUILDER_ATTR`` attribute.
        InvalidAgentBuilderTypeError: If that attribute isn't an
            ``LLMAgentBuilder`` instance.
        AgentBuilderNotReadyError: If the builder has no ``llm`` set.
        InvalidDefaultTaskTypeError: If ``DEFAULT_TASK_ATTR`` is
            present but isn't a ``Task`` instance.
    """
    if not script_path.is_file():
        raise ScriptNotFoundError(script_path)

    resolved_path = script_path.resolve()

    # A unique suffix (not just the stem) keeps two different scripts
    # that happen to share a filename in different directories from
    # colliding in sys.modules.
    unique_suffix = uuid.uuid4().hex
    module_name = f"_ai_entrypoint_{script_path.stem}_{unique_suffix}"
    spec = importlib.util.spec_from_file_location(module_name, resolved_path)
    if spec is None or spec.loader is None:
        raise ScriptImportError(
            script_path,
            ImportError(f"could not build an import spec for {script_path}"),
        )

    # Mirrors `python /path/to/main.py`: the script's own directory
    # goes on sys.path so sibling imports (`import utils`) resolve
    # the same way they would running it directly, regardless of the
    # cwd `agent-inspector launch` was invoked from. Left in place
    # (not popped after import) since the script's tool functions may
    # do their own lazy/deferred imports of sibling modules later, for
    # the lifetime of the process.
    script_dir = str(resolved_path.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

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

    default_task: Task | None = None
    if hasattr(module, DEFAULT_TASK_ATTR):
        default_task = getattr(module, DEFAULT_TASK_ATTR)
        if not isinstance(default_task, Task):
            raise InvalidDefaultTaskTypeError(script_path, default_task)

    return DiscoveredEntrypoint(
        agent_builder=agent_builder,
        default_task=default_task,
    )
