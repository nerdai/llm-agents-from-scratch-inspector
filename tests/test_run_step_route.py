"""Tests for ``POST /api/sessions/{id}/run-step`` (issue #5).

Exercises the route end-to-end through a real ``LLMAgent`` +
``SupervisedTaskHandler`` with a scripted (but otherwise real) LLM
that decides to call the ``next_number`` tool -- so these tests verify
the framework's actual tool-calling loop inside ``run_step`` executes
the real, registered ``SimpleFunctionTool``, not a stub, and that the
resulting ``tool_calls[]`` trace is captured correctly.

Session/step setup is built directly against ``SessionService`` and
the framework (rather than via the create-session/next-step routes
from issues #3/#4, which may not be merged yet) per this issue's
scope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from llm_agents_from_scratch import LLMAgent
from llm_agents_from_scratch.base.llm import BaseLLM, StructuredOutputType
from llm_agents_from_scratch.base.tool import BaseTool, Tool
from llm_agents_from_scratch.data_structures import (
    ChatMessage,
    ChatRole,
    CompleteResult,
    Task,
    TaskStep,
    ToolCall,
    ToolCallResult,
)
from llm_agents_from_scratch.data_structures.skill import SkillScope
from llm_agents_from_scratch.tools.simple_function import SimpleFunctionTool

from agent_inspector.deps import get_session_service
from agent_inspector.server import create_app
from agent_inspector.services.session import Session, SessionService

_SECOND_STEP_COUNTER = 2


def next_number(x: int) -> int:
    """The only real M1 tool: returns the next number after ``x``."""
    return x + 1


class _RawRaisingTool(BaseTool):
    """A tool with no internal error handling that always raises (#26).

    Deliberately *not* a ``SimpleFunctionTool``: that wrapper already
    catches whatever the wrapped Python function raises and reports it
    as a ``ToolCallResult(error=True, ...)`` -- it never actually
    raises out of ``__call__``. This class instead mirrors ``MCPTool``
    (``tools/mcp/tool.py`` in the framework), which has no internal
    try/except around ``session.call_tool()`` at all, so a transport
    failure there -- like this tool's ``RuntimeError`` -- propagates
    straight out of ``__call__`` and up through the framework's
    tool-calling loop. That's the case ``ToolExecutionError`` exists to
    catch at the source (see
    ``_RecordingSyncTool``/``_RecordingAsyncTool`` in
    ``services/session.py``).
    """

    @property
    def name(self) -> str:
        """Name of tool."""
        return "raising_tool"

    @property
    def description(self) -> str:
        """Description of tool."""
        return "A tool that always raises."

    @property
    def parameters_json_schema(self) -> dict[str, Any]:
        """JSON schema of tool parameters."""
        return {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        }

    def __call__(
        self,
        tool_call: ToolCall,
        *args: Any,
        **kwargs: Any,
    ) -> ToolCallResult:
        """Always raise, with no internal error handling."""
        raise RuntimeError("boom from tool")


def _write_skill(root: Path, name: str) -> None:
    """Write a minimal, valid on-disk skill under ``root/.agents/skills``.

    Same pattern as ``test_create_session.py``'s ``_write_skill`` --
    ``discover_skills`` resolves ``SkillScope.PROJECT`` to ``Path.cwd()
    / SKILL_SUBDIR``, so tests pair this with ``monkeypatch.chdir(root)``.

    Args:
        root (Path): Directory to create ``.agents/skills/<name>/``
            under (typically a ``tmp_path`` fixture).
        name (str): The skill's name (must match the directory name).
    """
    skill_dir = root / ".agents" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: A test skill.\n---\n\n"
        "Skill body content, non-empty as the framework requires.\n",
    )


class _ScriptedLLM(BaseLLM):
    """A minimal, real ``BaseLLM`` that scripts one tool-calling turn.

    Mirrors the mocking pattern used by the framework's own tests
    (``tests/agent/test_task_handler.py``): a concrete ``BaseLLM``
    subclass rather than mocking ``run_step`` itself, so the real
    tool-calling loop inside ``run_step`` actually runs.
    """

    def __init__(
        self,
        tool_call: ToolCall | None,
        final_content: str = "The next number is 5.",
        chat_error: Exception | None = None,
    ) -> None:
        self._tool_call = tool_call
        self._final_content = final_content
        self._chat_error = chat_error

    async def complete(self, prompt: str, **kwargs: Any) -> CompleteResult:
        return CompleteResult(response="mock", prompt=prompt)

    async def structured_output(
        self,
        prompt: str,
        mdl: type[StructuredOutputType],
        **kwargs: Any,
    ) -> StructuredOutputType:
        return mdl()

    async def chat(
        self,
        input: str,
        chat_history: Sequence[ChatMessage] | None = None,
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[ChatMessage, ChatMessage]:
        if self._chat_error is not None:
            raise self._chat_error
        tool_calls = [self._tool_call] if self._tool_call else None
        return (
            ChatMessage(role=ChatRole.USER, content=input),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content="I will call next_number." if tool_calls else "Done.",
                tool_calls=tool_calls,
            ),
        )

    async def continue_chat_with_tool_results(
        self,
        tool_call_results: Sequence[ToolCallResult],
        chat_history: Sequence[ChatMessage],
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[list[ChatMessage], ChatMessage]:
        return (
            [
                ChatMessage(role=ChatRole.TOOL, content=str(r.content))
                for r in tool_call_results
            ],
            ChatMessage(role=ChatRole.ASSISTANT, content=self._final_content),
        )


async def _build_session(
    session_service: SessionService,
    llm: BaseLLM,
    *,
    need: str = "run",
    tools: Sequence[Any] | None = None,
) -> tuple[Session, Any]:
    """Build a Session with a real LLMAgent + SupervisedTaskHandler.

    Registers the ``next_number`` tool by default (or ``tools``, if
    given -- e.g. #26's ``raising_tool``), obtains a pending
    ``TaskStep`` via ``handler.get_next_step(None)`` (no LLM call
    needed for the first step), and stashes it on the session the way
    #4's next-step endpoint is expected to.

    Returns:
        tuple[Session, Any]: The created session and the TaskStep that
            was set as ``pending_step``.
    """
    default_tools = [SimpleFunctionTool(next_number)]
    agent = LLMAgent(
        llm=llm,
        tools=list(tools) if tools is not None else default_tools,
    )
    task = Task(instruction="Figure out the next number after 4.")
    handler = await agent.run_supervised(task)
    step = await handler.get_next_step(None)
    # get_next_step(None) always returns a TaskStep (never a TaskResult):
    # see LLMAgent.TaskHandler.get_next_step's `if not previous_step_result`
    # branch.
    assert isinstance(step, TaskStep)

    session = session_service.create_session(agent=agent, handler=handler)
    session.pending_step = step
    session.need = need  # type: ignore[assignment]
    return session, step


@pytest.fixture
def session_service() -> SessionService:
    """A fresh, isolated SessionService per test."""
    return SessionService()


@pytest.fixture
def client(session_service: SessionService) -> TestClient:
    """A TestClient wired to the given isolated SessionService."""
    app = create_app(serve_static=False)
    app.dependency_overrides[get_session_service] = lambda: session_service
    return TestClient(app)


class TestRunStepSuccess:
    """Happy path: real tool execution + trace capture."""

    async def test_run_step_executes_real_tool_and_returns_trace(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """next_number actually executes; trace + result are returned."""
        tool_call = ToolCall(tool_name="next_number", arguments={"x": 4})
        llm = _ScriptedLLM(tool_call=tool_call, final_content="It's 5.")
        session, _ = await _build_session(session_service, llm)

        response = client.post(f"/api/sessions/{session.id}/run-step")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()

        assert body["result"]["content"] == "It's 5."
        assert body["result"]["task_step_id"]

        assert body["tool_calls"] == [
            {
                "tool_name": "next_number",
                "args": {"x": 4},
                "content": "5",
                "error": False,
            },
        ]

        assert body["step_counter"] == 1
        assert body["need"] == "next"

    async def test_run_step_transitions_need_and_clears_pending_step(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """On success, need -> 'next' and pending_step is cleared."""
        tool_call = ToolCall(tool_name="next_number", arguments={"x": 1})
        llm = _ScriptedLLM(tool_call=tool_call)
        session, _ = await _build_session(session_service, llm)

        client.post(f"/api/sessions/{session.id}/run-step")

        assert session.need == "next"
        assert session.pending_step is None

    async def test_run_step_without_tool_calls(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A step that needs no tool calls returns an empty trace.

        With no tool call scripted, the framework never invokes
        ``continue_chat_with_tool_results``, so the step result content
        comes straight from ``chat()``'s response message ("Done.").
        """
        llm = _ScriptedLLM(tool_call=None)
        session, _ = await _build_session(session_service, llm)

        response = client.post(f"/api/sessions/{session.id}/run-step")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["tool_calls"] == []
        assert body["result"]["content"] == "Done."

    async def test_run_step_second_call_increments_counter(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """step_counter reflects the framework handler's own count.

        Simulates #4 (next-step) handing the session a second pending
        ``TaskStep`` after the first run-step call completes.
        """
        tool_call = ToolCall(tool_name="next_number", arguments={"x": 1})
        llm = _ScriptedLLM(tool_call=tool_call)
        session, _ = await _build_session(session_service, llm)

        first = client.post(f"/api/sessions/{session.id}/run-step")
        assert first.json()["step_counter"] == 1

        session.pending_step = TaskStep(
            task_id=session.handler.task.id_,
            instruction="one more step",
        )
        session.need = "run"  # type: ignore[assignment]

        second = client.post(f"/api/sessions/{session.id}/run-step")

        assert second.status_code == status.HTTP_200_OK
        assert second.json()["step_counter"] == _SECOND_STEP_COUNTER


class TestRunStepSkillInvocation:
    """A ``from_scratch__use_skill`` call is captured in the trace.

    Regression coverage: ``from_scratch__use_skill`` isn't registered
    in ``agent.tools_registry`` like a regular tool -- the framework
    resolves it via the handler's separate ``_use_skill_tool``
    attribute instead (``TaskHandler.run_step``). Wrapping only
    ``tools_registry`` for recording silently missed every skill
    invocation: the skill still activated for real, but ``tool_calls``
    came back empty with no trace of what happened.
    """

    async def test_use_skill_call_appears_in_trace(
        self,
        client: TestClient,
        session_service: SessionService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The skill's real activation content lands in the trace."""
        _write_skill(tmp_path, "greeter")
        monkeypatch.chdir(tmp_path)

        tool_call = ToolCall(
            tool_name="from_scratch__use_skill",
            arguments={"name": "greeter"},
        )
        llm = _ScriptedLLM(tool_call=tool_call, final_content="Activated.")
        agent = LLMAgent(llm=llm, tools=[])
        task = Task(instruction="Use the greeter skill.")
        handler = await agent.run_supervised(
            task,
            skills_scopes=[SkillScope.PROJECT],
        )
        assert handler._use_skill_tool is not None  # sanity: skill wired up

        step = await handler.get_next_step(None)
        assert isinstance(step, TaskStep)
        session = session_service.create_session(agent=agent, handler=handler)
        session.pending_step = step
        session.need = "run"  # type: ignore[assignment]

        response = client.post(f"/api/sessions/{session.id}/run-step")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert len(body["tool_calls"]) == 1
        trace = body["tool_calls"][0]
        assert trace["tool_name"] == "from_scratch__use_skill"
        assert trace["args"] == {"name": "greeter"}
        assert trace["error"] is False
        assert '<skill_content name="greeter">' in trace["content"]

        # Also accumulates onto the session's cross-call history (#15),
        # same as any other tool call.
        assert len(session.tool_call_history) == 1
        assert session.tool_call_history[0].tool_name == (
            "from_scratch__use_skill"
        )

        # The wrapper is unwrapped again afterwards -- the handler's
        # real UseSkillTool is restored, not left wrapped indefinitely.
        assert handler._use_skill_tool is not None
        assert type(handler._use_skill_tool).__name__ == "UseSkillTool"


class TestRunStepWrongNeed:
    """409 when need != 'run'."""

    async def test_run_step_wrong_need_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A session at need='next' rejects run-step with 409."""
        llm = _ScriptedLLM(tool_call=None)
        session, _ = await _build_session(session_service, llm, need="next")

        response = client.post(f"/api/sessions/{session.id}/run-step")

        assert response.status_code == status.HTTP_409_CONFLICT


class TestRunStepNotFound:
    """404 for an unknown session id."""

    def test_run_step_unknown_session_returns_404(
        self,
        client: TestClient,
    ) -> None:
        """A bogus session id returns 404."""
        response = client.post("/api/sessions/sess_does-not-exist/run-step")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestRunStepLLMFailure:
    """502 when the framework raises during step execution."""

    async def test_run_step_llm_failure_returns_502(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """An LLM/network failure inside run_step maps to 502."""
        llm = _ScriptedLLM(tool_call=None, chat_error=RuntimeError("boom"))
        session, _ = await _build_session(session_service, llm)

        response = client.post(f"/api/sessions/{session.id}/run-step")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    async def test_run_step_llm_failure_leaves_need_unchanged(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A failed run-step call does not advance the need machine."""
        llm = _ScriptedLLM(tool_call=None, chat_error=RuntimeError("boom"))
        session, _ = await _build_session(session_service, llm)

        client.post(f"/api/sessions/{session.id}/run-step")

        assert session.need == "run"
        assert session.pending_step is not None


class TestRunStepToolFailure:
    """502 when a tool call itself raises, distinct from an LLM failure (#26).

    A tool raising (e.g. an MCPTool transport failure -- MCPTool.__call__
    has no internal try/except around session.call_tool(), so a
    transport failure there propagates straight through) is caught at
    the source by the tool-recording wrapper and raised as a
    ToolExecutionError, not the generic StepExecutionError an
    LLM/framework failure produces -- both map to 502, but with
    distinguishable messages.
    """

    async def test_run_step_tool_failure_returns_502(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A tool that raises maps to 502, not the wrong status code."""
        tool_call = ToolCall(tool_name="raising_tool", arguments={"x": 1})
        llm = _ScriptedLLM(tool_call=tool_call)
        session, _ = await _build_session(
            session_service,
            llm,
            tools=[_RawRaisingTool()],
        )

        response = client.post(f"/api/sessions/{session.id}/run-step")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    async def test_run_step_tool_failure_message_names_the_tool(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """The 502 detail names the failing tool, unlike an LLM failure."""
        tool_call = ToolCall(tool_name="raising_tool", arguments={"x": 1})
        llm = _ScriptedLLM(tool_call=tool_call)
        session, _ = await _build_session(
            session_service,
            llm,
            tools=[_RawRaisingTool()],
        )

        response = client.post(f"/api/sessions/{session.id}/run-step")

        detail = response.json()["detail"]
        assert "raising_tool" in detail
        assert "tool call to" in detail

    async def test_run_step_tool_failure_distinct_from_llm_failure(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A tool failure's 502 message differs from an LLM failure's.

        Regression coverage for the ticket's core complaint: before
        #26, both cases wrapped the underlying exception identically
        (StepExecutionError around whatever run_step raised), so a
        caller couldn't tell a tool-call failure from an
        LLM/framework-level one from the response alone.
        """
        tool_call = ToolCall(tool_name="raising_tool", arguments={"x": 1})
        tool_llm = _ScriptedLLM(tool_call=tool_call)
        tool_session, _ = await _build_session(
            session_service,
            tool_llm,
            tools=[_RawRaisingTool()],
        )
        tool_response = client.post(
            f"/api/sessions/{tool_session.id}/run-step",
        )

        llm_failure = _ScriptedLLM(
            tool_call=None,
            chat_error=RuntimeError("boom"),
        )
        llm_session, _ = await _build_session(session_service, llm_failure)
        llm_response = client.post(f"/api/sessions/{llm_session.id}/run-step")

        assert tool_response.status_code == status.HTTP_502_BAD_GATEWAY
        assert llm_response.status_code == status.HTTP_502_BAD_GATEWAY
        assert tool_response.json()["detail"] != llm_response.json()["detail"]

    async def test_run_step_tool_failure_leaves_need_unchanged(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A failed tool call does not advance the need machine either."""
        tool_call = ToolCall(tool_name="raising_tool", arguments={"x": 1})
        llm = _ScriptedLLM(tool_call=tool_call)
        session, _ = await _build_session(
            session_service,
            llm,
            tools=[_RawRaisingTool()],
        )

        client.post(f"/api/sessions/{session.id}/run-step")

        assert session.need == "run"
        assert session.pending_step is not None


class TestRunStepSessionBusy:
    """409 when the session already has a mutating call in flight (#26)."""

    async def test_run_step_busy_session_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A run-step call while the session's lock is held gets 409."""
        llm = _ScriptedLLM(tool_call=None)
        session, _ = await _build_session(session_service, llm)

        with session_service.lock_session(session.id):
            response = client.post(f"/api/sessions/{session.id}/run-step")

        assert response.status_code == status.HTTP_409_CONFLICT
