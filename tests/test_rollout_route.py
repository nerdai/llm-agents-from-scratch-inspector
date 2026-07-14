"""Tests for ``GET /api/sessions/{id}/rollout`` (TRD §6.8, issue #15).

Drives a real ``LLMAgent`` + ``SupervisedTaskHandler`` through a real
``run_step()`` call (mirroring ``tests/test_run_step_route.py``'s
mocking pattern) so ``handler.rollout`` holds real, non-trivial text,
proving the route returns the framework's own rollout string verbatim
rather than some reconstruction of it.
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
from agent_inspector.services.session import Session, SessionService


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


async def _build_fresh_session(session_service: SessionService) -> Session:
    """Build a brand-new session with no ``run_step()`` calls yet."""
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


class TestGetRolloutSuccess:
    """Happy path: the route returns ``handler.rollout`` verbatim."""

    async def test_rollout_fresh_session_is_empty(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A fresh session (no run-step yet) has an empty rollout."""
        session = await _build_fresh_session(session_service)

        response = client.get(f"/api/sessions/{session.id}/rollout")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"rollout": ""}

    async def test_rollout_after_run_step_matches_handler(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """After a real run-step, the route mirrors ``handler.rollout``."""
        session = await _build_session_after_run_step(session_service)

        response = client.get(f"/api/sessions/{session.id}/rollout")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["rollout"] == session.handler.rollout
        assert "It's 5." in body["rollout"]


class TestGetRolloutNotFound:
    """404 for an unknown session id."""

    def test_rollout_unknown_session_returns_404(
        self,
        client: TestClient,
    ) -> None:
        """A bogus session id returns 404."""
        response = client.get("/api/sessions/sess_does-not-exist/rollout")

        assert response.status_code == status.HTTP_404_NOT_FOUND
