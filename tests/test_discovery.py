"""Tests for convention-based entrypoint discovery (#47, ADR-002; #86).

Exercises ``discover_entrypoint`` against real, on-disk fixture
scripts written to ``tmp_path`` -- covering every failure mode the
issue calls out (missing script, import-time failure, missing
``agent_builder``, wrong type, builder with no ``llm`` set, wrongly-
typed ``default_task``) plus the happy path (with and without a
``default_task``), and asserting each raises the specific, actionable
exception rather than letting a raw traceback propagate.
"""

from pathlib import Path

import pytest
from llm_agents_from_scratch import LLMAgentBuilder
from llm_agents_from_scratch.data_structures import Task

from agent_inspector.discovery import discover_entrypoint
from agent_inspector.errors.discovery import (
    AGENT_BUILDER_ATTR,
    DEFAULT_TASK_ATTR,
    AgentBuilderNotReadyError,
    EntrypointDiscoveryError,
    InvalidAgentBuilderTypeError,
    InvalidDefaultTaskTypeError,
    MissingAgentBuilderError,
    ScriptImportError,
    ScriptNotFoundError,
)

_VALID_SCRIPT = """
from llm_agents_from_scratch import LLMAgentBuilder
from llm_agents_from_scratch.base.llm import BaseLLM


class _FakeLLM(BaseLLM):
    async def complete(self, prompt, **kwargs):
        raise NotImplementedError

    async def structured_output(self, prompt, mdl, **kwargs):
        raise NotImplementedError

    async def chat(self, input, chat_history=None, tools=None, **kwargs):
        raise NotImplementedError

    async def continue_chat_with_tool_results(
        self, tool_call_results, chat_history, tools=None, **kwargs,
    ):
        raise NotImplementedError


agent_builder = LLMAgentBuilder().with_llm(_FakeLLM())
"""


def _write(tmp_path: Path, name: str, source: str) -> Path:
    """Write ``source`` to ``tmp_path/name`` and return its path."""
    script = tmp_path / name
    script.write_text(source)
    return script


class TestScriptNotFound:
    """A script path that doesn't exist on disk."""

    def test_missing_script_raises_script_not_found(
        self,
        tmp_path: Path,
    ) -> None:
        """A nonexistent path raises ScriptNotFoundError, not a raw error."""
        missing = tmp_path / "does_not_exist.py"

        with pytest.raises(ScriptNotFoundError):
            discover_entrypoint(missing)

    def test_directory_path_raises_script_not_found(
        self,
        tmp_path: Path,
    ) -> None:
        """A directory (not a file) is also reported as not found."""
        with pytest.raises(ScriptNotFoundError):
            discover_entrypoint(tmp_path)


class TestScriptImportFailure:
    """A script that exists but raises while being imported."""

    def test_syntax_error_is_wrapped(self, tmp_path: Path) -> None:
        """A script with a syntax error raises ScriptImportError."""
        script = _write(tmp_path, "broken.py", "def broken(:\n    pass\n")

        with pytest.raises(ScriptImportError):
            discover_entrypoint(script)

    def test_import_error_is_wrapped(self, tmp_path: Path) -> None:
        """A script importing a nonexistent module raises ScriptImportError."""
        script = _write(
            tmp_path,
            "bad_import.py",
            "import this_module_does_not_exist_anywhere\n",
        )

        with pytest.raises(ScriptImportError):
            discover_entrypoint(script)

    def test_error_at_module_scope_is_wrapped(self, tmp_path: Path) -> None:
        """An exception raised at module scope raises ScriptImportError."""
        script = _write(
            tmp_path,
            "raises.py",
            "raise RuntimeError('boom during import')\n",
        )

        with pytest.raises(ScriptImportError):
            discover_entrypoint(script)


class TestMissingAgentBuilder:
    """A script that imports cleanly but has no ``agent_builder``."""

    def test_missing_attribute_raises(self, tmp_path: Path) -> None:
        """No module-level ``agent_builder`` raises MissingAgentBuilderError."""
        script = _write(tmp_path, "no_builder.py", "x = 1\n")

        with pytest.raises(MissingAgentBuilderError):
            discover_entrypoint(script)


class TestInvalidAgentBuilderType:
    """A script whose ``agent_builder`` isn't an ``LLMAgentBuilder``."""

    def test_wrong_type_raises(self, tmp_path: Path) -> None:
        """A non-LLMAgentBuilder value raises InvalidAgentBuilderTypeError."""
        script = _write(
            tmp_path,
            "wrong_type.py",
            f"{AGENT_BUILDER_ATTR} = object()\n",
        )

        with pytest.raises(InvalidAgentBuilderTypeError):
            discover_entrypoint(script)


class TestAgentBuilderNotReady:
    """A discovered builder with no ``llm`` configured."""

    def test_missing_llm_raises(self, tmp_path: Path) -> None:
        """A builder with `llm` unset fails fast, per ADR-002 (#47)."""
        script = _write(
            tmp_path,
            "no_llm.py",
            f"from llm_agents_from_scratch import LLMAgentBuilder\n"
            f"{AGENT_BUILDER_ATTR} = LLMAgentBuilder()\n",
        )

        with pytest.raises(AgentBuilderNotReadyError):
            discover_entrypoint(script)


class TestInvalidDefaultTaskType:
    """A script whose ``default_task`` isn't a ``Task``."""

    def test_wrong_type_raises(self, tmp_path: Path) -> None:
        """A non-Task `default_task` raises InvalidDefaultTaskTypeError."""
        script = _write(
            tmp_path,
            "wrong_default_task.py",
            _VALID_SCRIPT + f"\n{DEFAULT_TASK_ATTR} = 'not a Task'\n",
        )

        with pytest.raises(InvalidDefaultTaskTypeError):
            discover_entrypoint(script)


class TestDiscoverEntrypointSuccess:
    """The happy path: a well-formed script with a ready builder."""

    def test_returns_the_discovered_builder(self, tmp_path: Path) -> None:
        """A valid script's `agent_builder` is returned as-is."""
        script = _write(tmp_path, "main.py", _VALID_SCRIPT)

        discovered = discover_entrypoint(script)

        assert isinstance(discovered.agent_builder, LLMAgentBuilder)
        assert discovered.agent_builder.llm is not None

    def test_no_default_task_is_none(self, tmp_path: Path) -> None:
        """A script with no `default_task` reports `None`, not an error."""
        script = _write(tmp_path, "main.py", _VALID_SCRIPT)

        discovered = discover_entrypoint(script)

        assert discovered.default_task is None

    def test_default_task_is_returned(self, tmp_path: Path) -> None:
        """A script's `default_task` (a real `Task`) is returned as-is."""
        script = _write(
            tmp_path,
            "main.py",
            _VALID_SCRIPT + "\n"
            "from llm_agents_from_scratch.data_structures import Task\n"
            f"{DEFAULT_TASK_ATTR} = Task(instruction='do the thing')\n",
        )

        discovered = discover_entrypoint(script)

        assert isinstance(discovered.default_task, Task)
        assert discovered.default_task.instruction == "do the thing"

    def test_two_scripts_are_independently_importable(
        self,
        tmp_path: Path,
    ) -> None:
        """Discovering from two different scripts doesn't collide."""
        first = _write(tmp_path, "first.py", _VALID_SCRIPT)
        second = _write(tmp_path, "second.py", _VALID_SCRIPT)

        discovered_one = discover_entrypoint(first)
        discovered_two = discover_entrypoint(second)

        assert discovered_one.agent_builder is not discovered_two.agent_builder

    def test_same_filename_in_different_directories_does_not_collide(
        self,
        tmp_path: Path,
    ) -> None:
        """Two scripts sharing a filename in different dirs don't collide.

        Regression test: the synthetic sys.modules name used to be
        derived from the script's stem alone, so `dir_a/main.py` and
        `dir_b/main.py` could clobber each other.
        """
        dir_a = tmp_path / "dir_a"
        dir_b = tmp_path / "dir_b"
        dir_a.mkdir()
        dir_b.mkdir()
        first = _write(dir_a, "main.py", _VALID_SCRIPT)
        second = _write(dir_b, "main.py", _VALID_SCRIPT)

        discovered_one = discover_entrypoint(first)
        discovered_two = discover_entrypoint(second)

        assert discovered_one.agent_builder is not discovered_two.agent_builder

    def test_sibling_module_import_resolves(self, tmp_path: Path) -> None:
        """A script that imports a sibling module in its own directory works.

        Regression test: the script's own directory wasn't being added
        to sys.path, so `import utils` (a module alongside the script,
        not on sys.path otherwise) would fail unless the CLI happened
        to be invoked from that same directory.
        """
        _write(tmp_path, "helper_module.py", "GREETING = 'hi from helper'\n")
        script = _write(
            tmp_path,
            "uses_sibling.py",
            "from llm_agents_from_scratch import LLMAgentBuilder\n"
            "from llm_agents_from_scratch.base.llm import BaseLLM\n"
            "import helper_module\n"
            "\n"
            "\n"
            "class _FakeLLM(BaseLLM):\n"
            "    async def complete(self, prompt, **kwargs):\n"
            "        raise NotImplementedError\n"
            "\n"
            "    async def structured_output(self, prompt, mdl, **kwargs):\n"
            "        raise NotImplementedError\n"
            "\n"
            "    async def chat(self, input, chat_history=None, tools=None, "
            "**kwargs):\n"
            "        raise NotImplementedError\n"
            "\n"
            "    async def continue_chat_with_tool_results(\n"
            "        self, tool_call_results, chat_history, tools=None, "
            "**kwargs,\n"
            "    ):\n"
            "        raise NotImplementedError\n"
            "\n"
            "\n"
            "assert helper_module.GREETING == 'hi from helper'\n"
            f"{AGENT_BUILDER_ATTR} = LLMAgentBuilder().with_llm(_FakeLLM())\n",
        )

        discovered = discover_entrypoint(script)

        assert isinstance(discovered.agent_builder, LLMAgentBuilder)


def test_all_discovery_errors_are_entrypoint_discovery_errors() -> None:
    """Every specific failure subclasses the one type ``cli.py`` catches."""
    for cls in (
        ScriptNotFoundError,
        ScriptImportError,
        MissingAgentBuilderError,
        InvalidAgentBuilderTypeError,
        AgentBuilderNotReadyError,
        InvalidDefaultTaskTypeError,
    ):
        assert issubclass(cls, EntrypointDiscoveryError)
