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

from typing import Any, Sequence

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from llm_agents_from_scratch import LLMAgent
from llm_agents_from_scratch.base.llm import BaseLLM, StructuredOutputType
from llm_agents_from_scratch.base.tool import Tool
from llm_agents_from_scratch.data_structures import (
    ChatMessage,
    ChatRole,
    CompleteResult,
    Task,
    TaskStep,
    ToolCall,
    ToolCallResult,
)
from llm_agents_from_scratch.tools.simple_function import SimpleFunctionTool

from agent_inspector.deps import get_session_service
from agent_inspector.server import create_app
from agent_inspector.services import Session, SessionService

_SECOND_STEP_COUNTER = 2


def next_number(x: int) -> int:
    """The only real M1 tool: returns the next number after ``x``."""
    return x + 1


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
) -> tuple[Session, Any]:
    """Build a Session with a real LLMAgent + SupervisedTaskHandler.

    Registers the ``next_number`` tool, obtains a pending ``TaskStep``
    via ``handler.get_next_step(None)`` (no LLM call needed for the
    first step), and stashes it on the session the way #4's
    next-step endpoint is expected to.

    Returns:
        tuple[Session, Any]: The created session and the TaskStep that
            was set as ``pending_step``.
    """
    agent = LLMAgent(llm=llm, tools=[SimpleFunctionTool(next_number)])
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
