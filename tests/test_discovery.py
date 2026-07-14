"""Tests for convention-based entrypoint discovery (#47, ADR-002).

Exercises ``discover_agent_builder`` against real, on-disk fixture
scripts written to ``tmp_path`` -- covering every failure mode the
issue calls out (missing script, import-time failure, missing
``agent_builder``, wrong type, builder with no ``llm`` set) plus the
happy path, and asserting each raises the specific, actionable
exception rather than letting a raw traceback propagate.
"""

from pathlib import Path

import pytest
from llm_agents_from_scratch import LLMAgentBuilder

from agent_inspector.discovery import discover_agent_builder
from agent_inspector.errors.discovery import (
    AGENT_BUILDER_ATTR,
    AgentBuilderNotReadyError,
    EntrypointDiscoveryError,
    InvalidAgentBuilderTypeError,
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
            discover_agent_builder(missing)

    def test_directory_path_raises_script_not_found(
        self,
        tmp_path: Path,
    ) -> None:
        """A directory (not a file) is also reported as not found."""
        with pytest.raises(ScriptNotFoundError):
            discover_agent_builder(tmp_path)


class TestScriptImportFailure:
    """A script that exists but raises while being imported."""

    def test_syntax_error_is_wrapped(self, tmp_path: Path) -> None:
        """A script with a syntax error raises ScriptImportError."""
        script = _write(tmp_path, "broken.py", "def broken(:\n    pass\n")

        with pytest.raises(ScriptImportError):
            discover_agent_builder(script)

    def test_import_error_is_wrapped(self, tmp_path: Path) -> None:
        """A script importing a nonexistent module raises ScriptImportError."""
        script = _write(
            tmp_path,
            "bad_import.py",
            "import this_module_does_not_exist_anywhere\n",
        )

        with pytest.raises(ScriptImportError):
            discover_agent_builder(script)

    def test_error_at_module_scope_is_wrapped(self, tmp_path: Path) -> None:
        """An exception raised at module scope raises ScriptImportError."""
        script = _write(
            tmp_path,
            "raises.py",
            "raise RuntimeError('boom during import')\n",
        )

        with pytest.raises(ScriptImportError):
            discover_agent_builder(script)


class TestMissingAgentBuilder:
    """A script that imports cleanly but has no ``agent_builder``."""

    def test_missing_attribute_raises(self, tmp_path: Path) -> None:
        """No module-level ``agent_builder`` raises MissingAgentBuilderError."""
        script = _write(tmp_path, "no_builder.py", "x = 1\n")

        with pytest.raises(MissingAgentBuilderError):
            discover_agent_builder(script)


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
            discover_agent_builder(script)


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
            discover_agent_builder(script)


class TestDiscoverAgentBuilderSuccess:
    """The happy path: a well-formed script with a ready builder."""

    def test_returns_the_discovered_builder(self, tmp_path: Path) -> None:
        """A valid script's `agent_builder` is returned as-is."""
        script = _write(tmp_path, "main.py", _VALID_SCRIPT)

        builder = discover_agent_builder(script)

        assert isinstance(builder, LLMAgentBuilder)
        assert builder.llm is not None

    def test_two_scripts_are_independently_importable(
        self,
        tmp_path: Path,
    ) -> None:
        """Discovering from two different scripts doesn't collide."""
        first = _write(tmp_path, "first.py", _VALID_SCRIPT)
        second = _write(tmp_path, "second.py", _VALID_SCRIPT)

        builder_one = discover_agent_builder(first)
        builder_two = discover_agent_builder(second)

        assert builder_one is not builder_two

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

        builder_one = discover_agent_builder(first)
        builder_two = discover_agent_builder(second)

        assert builder_one is not builder_two

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

        builder = discover_agent_builder(script)

        assert isinstance(builder, LLMAgentBuilder)


def test_all_discovery_errors_are_entrypoint_discovery_errors() -> None:
    """Every specific failure subclasses the one type ``cli.py`` catches."""
    for cls in (
        ScriptNotFoundError,
        ScriptImportError,
        MissingAgentBuilderError,
        InvalidAgentBuilderTypeError,
        AgentBuilderNotReadyError,
    ):
        assert issubclass(cls, EntrypointDiscoveryError)
