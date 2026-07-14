"""Tests for ``GET /api/sessions/{id}`` (TRD §6.7, issue #15).

Covers the session-state endpoint at various points in the ``need``
lifecycle: a fresh session, after a real ``run_step()`` call (proving
``Session.tool_call_history`` -- new bookkeeping added by this issue --
actually accumulates a trace end-to-end), after the operator approves
the pending result (proving ``final_result`` is recovered from the
framework handler's own resolved ``asyncio.Future`` once
``pending_result`` is cleared), and 404 for an unknown session.
"""

from __future__ import annotations

from typing import Any, Sequence
from unittest.mock import AsyncMock

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
    NextStepDecision,
    Task,
    TaskResult,
    TaskStep,
    TaskStepResult,
    ToolCall,
    ToolCallResult,
)
from llm_agents_from_scratch.tools.simple_function import SimpleFunctionTool

from agent_inspector.deps import get_session_service
from agent_inspector.server import create_app
from agent_inspector.services.session import Session, SessionService

_SECOND_STEP_COUNTER = 2
_SECOND_TOOL_CALL_HISTORY_LEN = 2


def next_number(x: int) -> int:
    """The only real M1 tool: returns the next number after ``x``."""
    return x + 1


class _ScriptedLLM(BaseLLM):
    """A minimal, real ``BaseLLM`` that scripts one tool-calling turn.

    Same pattern as ``tests/test_run_step_route.py``'s ``_ScriptedLLM``.
    """

    def __init__(
        self,
        tool_call: ToolCall | None,
        final_content: str = "The next number is 5.",
    ) -> None:
        self._tool_call = tool_call
        self._final_content = final_content

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


async def _build_fresh_session(session_service: SessionService) -> Session:
    """Build a brand-new session, still at ``need == "next"``."""
    llm = _ScriptedLLM(tool_call=None)
    agent = LLMAgent(llm=llm, tools=[SimpleFunctionTool(next_number)])
    task = Task(instruction="Figure out the next number after 4.")
    handler = await agent.run_supervised(task)
    return session_service.create_session(agent=agent, handler=handler)


async def _build_session_after_run_step(
    session_service: SessionService,
) -> Session:
    """Build a session that has completed one real ``run_step()`` call."""
    tool_call = ToolCall(tool_name="next_number", arguments={"x": 4})
    llm = _ScriptedLLM(tool_call=tool_call, final_content="It's 5.")
    agent = LLMAgent(llm=llm, tools=[SimpleFunctionTool(next_number)])
    task = Task(instruction="Figure out the next number after 4.")
    handler = await agent.run_supervised(task)
    step = await handler.get_next_step(None)
    assert isinstance(step, TaskStep)

    session = session_service.create_session(agent=agent, handler=handler)
    session.pending_step = step
    session.need = "run"  # type: ignore[assignment]

    await session_service.run_step(session)
    return session


async def _build_session_at_approve(
    session_service: SessionService,
) -> tuple[Session, TaskResult]:
    """Build a session parked at ``need == "approve"`` with a pending result.

    Mirrors ``tests/test_complete_route.py``'s
    ``_drive_session_to_approve``.
    """
    llm = AsyncMock()
    llm.structured_output.return_value = NextStepDecision(
        kind="final_result",
        content="unused for final_result",
    )
    agent = LLMAgent(llm=llm)
    task = Task(instruction="do something")
    handler = await agent.run_supervised(task)

    first_step = await handler.get_next_step(None)
    assert isinstance(first_step, TaskStep)

    step_result = TaskStepResult(
        task_step_id=first_step.id_,
        content="stub step content",
    )
    final_result = await handler.get_next_step(step_result)
    assert isinstance(final_result, TaskResult)

    session = session_service.create_session(agent=agent, handler=handler)
    session.pending_result = final_result
    session_service.transition_need(session, "approve")

    return session, final_result


class TestGetSessionStateFresh:
    """A fresh session (need='next', no run-step yet)."""

    async def test_fresh_session_state(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Fresh state: empty rollout/history, no final result."""
        session = await _build_fresh_session(session_service)

        response = client.get(f"/api/sessions/{session.id}")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["session_id"] == session.id
        assert body["need"] == "next"
        assert body["step_counter"] == 0
        assert body["rollout"] == ""
        assert body["tool_call_history"] == []
        assert body["final_result"] is None
        assert body["config"]["tools"] == ["next_number"]
        assert body["config"]["skills"] == []


class TestGetSessionStateAfterRunStep:
    """After one real ``run_step()`` call (need='next' again)."""

    async def test_state_after_run_step_accumulates_tool_call_history(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """tool_call_history reflects the real tool call run-step made.

        This is the key assertion proving the new
        ``Session.tool_call_history`` bookkeeping actually works
        end-to-end: nothing before this issue persisted a call trace
        across ``run_step()`` calls.
        """
        session = await _build_session_after_run_step(session_service)

        response = client.get(f"/api/sessions/{session.id}")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["need"] == "next"
        assert body["step_counter"] == 1
        assert "It's 5." in body["rollout"]
        assert body["tool_call_history"] == [
            {
                "tool_name": "next_number",
                "args": {"x": 4},
                "content": "5",
                "error": False,
            },
        ]
        assert body["final_result"] is None

    async def test_state_after_second_run_step_appends_history(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A second run-step call appends to, rather than replaces, history."""
        session = await _build_session_after_run_step(session_service)

        session.pending_step = TaskStep(
            task_id=session.handler.task.id_,
            instruction="one more step",
        )
        session.need = "run"  # type: ignore[assignment]
        session.agent.llm._tool_call = ToolCall(
            tool_name="next_number",
            arguments={"x": 5},
        )
        session.agent.llm._final_content = "It's 6."
        await session_service.run_step(session)

        response = client.get(f"/api/sessions/{session.id}")

        body = response.json()
        assert body["step_counter"] == _SECOND_STEP_COUNTER
        assert len(body["tool_call_history"]) == _SECOND_TOOL_CALL_HISTORY_LEN
        assert body["tool_call_history"][0]["args"] == {"x": 4}
        assert body["tool_call_history"][1]["args"] == {"x": 5}


class TestGetSessionStateApprove:
    """A session awaiting operator approval (need='approve')."""

    async def test_final_result_reflects_pending_result(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """final_result mirrors the proposed (not yet approved) result."""
        session, expected_result = await _build_session_at_approve(
            session_service,
        )

        response = client.get(f"/api/sessions/{session.id}")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["need"] == "approve"
        assert body["final_result"] == {
            "task_id": expected_result.task_id,
            "content": expected_result.content,
        }


class TestGetSessionStateDone:
    """A session that has been approved (need='done')."""

    async def test_final_result_recovered_after_complete(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """final_result is recovered from the resolved handler future.

        ``complete()`` clears ``session.pending_result``, so this
        proves ``get_session_state`` correctly falls back to
        ``handler.result()`` rather than losing the final result once
        the operator approves it.
        """
        session, expected_result = await _build_session_at_approve(
            session_service,
        )
        await session_service.complete(session)
        assert session.need == "done"
        assert session.pending_result is None

        response = client.get(f"/api/sessions/{session.id}")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["need"] == "done"
        assert body["final_result"] == {
            "task_id": expected_result.task_id,
            "content": expected_result.content,
        }

    async def test_final_result_none_after_abort(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """An aborted session has no final result to report."""
        session = await _build_fresh_session(session_service)
        await session_service.abort(session)
        assert session.need == "done"

        response = client.get(f"/api/sessions/{session.id}")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["need"] == "done"
        assert body["final_result"] is None


class TestGetSessionStateNotFound:
    """404 for an unknown session id."""

    def test_unknown_session_returns_404(self, client: TestClient) -> None:
        """A bogus session id returns 404."""
        response = client.get("/api/sessions/sess_does-not-exist")

        assert response.status_code == status.HTTP_404_NOT_FOUND
