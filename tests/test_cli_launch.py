"""Tests for ``agent-inspector launch <script>`` (#47, ADR-002).

Exercises the CLI's discovery-then-serve wiring via Typer's own
``CliRunner``, mocking ``uvicorn.run`` so nothing actually binds a
socket. Covers the acceptance criteria that discovery failures surface
as a clear, actionable message and a nonzero exit code at launch time
-- not a raw traceback, and not a lazy failure on the first
``POST /sessions``.
"""

from pathlib import Path
from unittest.mock import patch

from llm_agents_from_scratch import LLMAgentBuilder
from typer.testing import CliRunner

from agent_inspector import cli, deps
from agent_inspector.discovery import AGENT_BUILDER_ATTR

runner = CliRunner()

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


class TestLaunchDiscoveryFailure:
    """A bad script fails at launch time with a clear message."""

    def test_missing_script_exits_nonzero_with_clear_message(self) -> None:
        """A nonexistent script path exits nonzero, no raw traceback."""
        result = runner.invoke(cli.app, ["launch", "does_not_exist.py"])

        assert result.exit_code != 0
        assert "Agent script not found" in result.output
        assert "Traceback" not in result.output

    def test_missing_agent_builder_exits_nonzero_with_clear_message(
        self,
        tmp_path: Path,
    ) -> None:
        """A script with no `agent_builder` exits nonzero with guidance."""
        script = tmp_path / "no_builder.py"
        script.write_text("x = 1\n")

        result = runner.invoke(cli.app, ["launch", str(script)])

        assert result.exit_code != 0
        assert AGENT_BUILDER_ATTR in result.output
        assert "Traceback" not in result.output

    def test_builder_without_llm_exits_nonzero_with_clear_message(
        self,
        tmp_path: Path,
    ) -> None:
        """A builder with no `llm` set fails fast at launch, per ADR-002."""
        script = tmp_path / "no_llm.py"
        script.write_text(
            "from llm_agents_from_scratch import LLMAgentBuilder\n"
            f"{AGENT_BUILDER_ATTR} = LLMAgentBuilder()\n",
        )

        result = runner.invoke(cli.app, ["launch", str(script)])

        assert result.exit_code != 0
        assert "llm" in result.output
        assert "Traceback" not in result.output


class TestLaunchDiscoverySuccess:
    """A well-formed script is discovered and wired up before serving."""

    def test_valid_script_configures_the_session_service(
        self,
        tmp_path: Path,
    ) -> None:
        """A valid script's builder ends up on the shared SessionService."""
        script = tmp_path / "main.py"
        script.write_text(_VALID_SCRIPT)

        with patch("agent_inspector.cli.uvicorn.run") as mock_run:
            result = runner.invoke(
                cli.app,
                ["launch", str(script), "--backend-only", "--no-open"],
            )

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        assert isinstance(deps._session_service.agent_builder, LLMAgentBuilder)
