"""Tests for ``POST /api/sessions/{id}/next-step`` (issue #4).

Exercises the route end-to-end via FastAPI's ``TestClient`` against a
real ``LLMAgent`` + ``SupervisedTaskHandler`` (issue #8's chapter),
with the backbone LLM swapped for a network-free stand-in mirroring
the pattern used in ``llm-agents-from-scratch``'s own
``tests/conftest.py::MockBaseLLM`` -- no Ollama daemon required.
"""

from __future__ import annotations

from typing import Any, Sequence

import pytest
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
    TaskStepResult,
    ToolCallResult,
)

from agent_inspector.deps import get_session_service
from agent_inspector.server import create_app
from agent_inspector.services import Session, SessionService

_HTTP_OK = 200
_HTTP_CONFLICT = 409
_HTTP_NOT_FOUND = 404


class _MockBaseLLM(BaseLLM):
    """Network-free ``BaseLLM`` stand-in for the overseer LLM.

    ``structured_output`` -- the only call
    ``SupervisedTaskHandler.get_next_step`` makes to the LLM -- always
    returns ``next_step_decision``. The remaining abstract methods are
    never exercised on the next-step path but are implemented so the
    class can be instantiated.
    """

    def __init__(self, next_step_decision: NextStepDecision) -> None:
        """Initialize with the canned ``NextStepDecision`` to return."""
        self._next_step_decision = next_step_decision

    async def complete(self, prompt: str, **kwargs: Any) -> CompleteResult:
        """Unused on the next-step path; provided to satisfy BaseLLM."""
        return CompleteResult(response="mock complete", prompt=prompt)

    async def structured_output(
        self,
        prompt: str,
        mdl: type[StructuredOutputType],
        **kwargs: Any,
    ) -> StructuredOutputType:
        """Return the canned decision, ignoring ``prompt``/``mdl``."""
        return self._next_step_decision  # type: ignore[return-value]

    async def chat(
        self,
        input: str,
        chat_history: Sequence[ChatMessage] | None = None,
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[ChatMessage, ChatMessage]:
        """Unused on the next-step path; provided to satisfy BaseLLM."""
        return (
            ChatMessage(role=ChatRole.USER, content=input),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content="mock chat response",
            ),
        )

    async def continue_chat_with_tool_results(
        self,
        tool_call_results: Sequence[ToolCallResult],
        chat_history: Sequence[ChatMessage],
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[list[ChatMessage], ChatMessage]:
        """Unused on the next-step path; provided to satisfy BaseLLM."""
        return (
            [],
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content="mock tool response",
            ),
        )


async def _new_session(
    service: SessionService,
    *,
    instruction: str = "count to three",
    next_step_decision: NextStepDecision | None = None,
) -> Session:
    """Create a session around a real, network-free supervised handler.

    Args:
        service (SessionService): The service to register the session
            on.
        instruction (str): The task instruction. Defaults to "count
            to three".
        next_step_decision (NextStepDecision | None): What the mocked
            overseer LLM should decide on any call that isn't the
            deterministic first call. Defaults to a "final_result"
            decision.

    Returns:
        Session: The newly created, stored session.
    """
    llm = _MockBaseLLM(
        next_step_decision or NextStepDecision(kind="final_result", content=""),
    )
    agent = LLMAgent(llm=llm)
    handler = await agent.run_supervised(Task(instruction=instruction))
    return service.create_session(agent=agent, handler=handler)


@pytest.fixture()
def session_service() -> SessionService:
    """A fresh, isolated ``SessionService`` for each test."""
    return SessionService()


@pytest.fixture()
def client(session_service: SessionService) -> TestClient:
    """A ``TestClient`` wired to ``session_service`` via dep override."""
    app = create_app(serve_static=False)
    app.dependency_overrides[get_session_service] = lambda: session_service
    return TestClient(app)


class TestPostNextStep:
    """``POST /api/sessions/{id}/next-step`` (TRD §6.2)."""

    async def test_first_call_wraps_task_deterministically(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """First call (no prior step) skips the LLM and wraps the task."""
        # decision below would blow up structured_output if it were
        # ever awaited on this call -- proves no LLM call was made.
        session = await _new_session(
            session_service,
            instruction="count to three",
            next_step_decision=NextStepDecision(
                kind="final_result",
                content="should not be used",
            ),
        )

        response = client.post(f"/api/sessions/{session.id}/next-step")

        assert response.status_code == _HTTP_OK
        body = response.json()
        assert body == {
            "kind": "next_step",
            "decision": {
                "kind": "next_step",
                "content": "count to three",
            },
            "step": {
                "id_": body["step"]["id_"],
                "task_id": session.handler.task.id_,
                "instruction": "count to three",
            },
            "need": "run",
        }
        assert session_service.get_session(session.id).need == "run"

    async def test_subsequent_call_routes_next_step_kind(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A later call routes through the overseer's next_step decision."""
        session = await _new_session(
            session_service,
            next_step_decision=NextStepDecision(
                kind="next_step",
                content="call the next_number tool with x=4.",
            ),
        )
        # Simulate a prior run-step cycle (issue #5's job in real use):
        # need is back at "next" and a previous result is on hand.
        session.last_step_result = TaskStepResult(
            task_step_id="prev-step-id",
            content="previous step content",
        )

        response = client.post(f"/api/sessions/{session.id}/next-step")

        assert response.status_code == _HTTP_OK
        body = response.json()
        assert body["kind"] == "next_step"
        assert body["need"] == "run"
        assert body["decision"] == {
            "kind": "next_step",
            "content": "call the next_number tool with x=4.",
        }
        assert body["step"]["instruction"] == (
            "call the next_number tool with x=4."
        )
        assert body["step"]["task_id"] == session.handler.task.id_
        assert session_service.get_session(session.id).need == "run"

    async def test_subsequent_call_routes_final_result_kind(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A later call routes through the overseer's final_result decision."""
        session = await _new_session(
            session_service,
            next_step_decision=NextStepDecision(
                kind="final_result",
                content="",
            ),
        )
        session.last_step_result = TaskStepResult(
            task_step_id="prev-step-id",
            content="1, 2, 3.",
        )

        response = client.post(f"/api/sessions/{session.id}/next-step")

        assert response.status_code == _HTTP_OK
        body = response.json()
        assert body == {
            "kind": "final_result",
            "result": {
                "task_id": session.handler.task.id_,
                "content": "1, 2, 3.",
            },
            "need": "approve",
        }
        assert session_service.get_session(session.id).need == "approve"

    async def test_wrong_need_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A session not waiting on "next" is rejected with 409."""
        session = await _new_session(session_service)
        session.need = "run"

        response = client.post(f"/api/sessions/{session.id}/next-step")

        assert response.status_code == _HTTP_CONFLICT

    async def test_unknown_session_returns_404(
        self,
        client: TestClient,
    ) -> None:
        """An unknown session id is reported as 404."""
        response = client.post("/api/sessions/sess_does-not-exist/next-step")

        assert response.status_code == _HTTP_NOT_FOUND
