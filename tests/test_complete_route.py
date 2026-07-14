"""Tests for ``POST /api/sessions/{id}/complete`` (TRD §6.4, issue #6).

Drives a real ``LLMAgent`` + ``SupervisedTaskHandler`` to
``need == "approve"`` by mocking the LLM's network call the same way
the framework's own tests do (``AsyncMock`` on ``structured_output``,
see ``llm-agents-from-scratch``'s ``tests/conftest.py`` /
``tests/agent/test_task_handler.py``), then exercises the route via
FastAPI's ``TestClient``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from llm_agents_from_scratch import LLMAgent
from llm_agents_from_scratch.data_structures import (
    NextStepDecision,
    Task,
    TaskResult,
    TaskStep,
    TaskStepResult,
)
from llm_agents_from_scratch.memory.memory import Memory

from agent_inspector.deps import get_session_service
from agent_inspector.server import create_app
from agent_inspector.services.session import Session, SessionService


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


async def _drive_session_to_approve(
    session_service: SessionService,
    *,
    memories: list[Memory] | None = None,
) -> tuple[Session, TaskResult]:
    """Build a session parked at ``need == "approve"`` with a pending result.

    Mocks the LLM's ``structured_output`` call (the only network call
    ``get_next_step`` makes) to immediately decide ``final_result``, so
    no real LLM/Ollama call is made -- mirrors the framework's own
    ``mock_llm`` fixture pattern.

    Args:
        session_service (SessionService): The service to register the
            session on.
        memories (list[Memory] | None): Memories to attach to the
            agent, if any.

    Returns:
        tuple[Session, TaskResult]: The registered session (already
            transitioned to ``need="approve"`` with ``pending_result``
            set) and the ``TaskResult`` it holds.
    """
    llm = AsyncMock()
    llm.structured_output.return_value = NextStepDecision(
        kind="final_result",
        content="unused for final_result",
    )
    agent = LLMAgent(llm=llm, memories=memories or [])
    task = Task(instruction="do something")
    handler = await agent.run_supervised(task)

    # first get_next_step (no previous result) -> TaskStep, no LLM call
    first_step = await handler.get_next_step(None)
    assert isinstance(first_step, TaskStep)

    # fabricate the step's result directly rather than driving run_step()
    # (which would exercise llm.chat / tool-calling -- out of scope here)
    step_result = TaskStepResult(
        task_step_id=first_step.id_,
        content="stub step content",
    )

    # second get_next_step consults the (mocked) LLM and concludes
    final_result = await handler.get_next_step(step_result)
    assert isinstance(final_result, TaskResult)

    session = session_service.create_session(agent=agent, handler=handler)
    session.pending_result = final_result
    session_service.transition_need(session, "approve")

    return session, final_result


class TestPostComplete:
    """``POST /api/sessions/{id}/complete`` (TRD §6.4)."""

    async def test_complete_returns_resolved_status_and_done_need(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Happy path: 200 with resolved status, result payload, need=done."""
        session, expected_result = await _drive_session_to_approve(
            session_service,
        )

        response = client.post(f"/api/sessions/{session.id}/complete")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "status": "resolved",
            "result": {
                "task_id": expected_result.task_id,
                "content": expected_result.content,
            },
            "need": "done",
        }

    async def test_complete_transitions_session_need_to_done(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """The session's need is updated to 'done' in the session store."""
        session, _ = await _drive_session_to_approve(session_service)

        client.post(f"/api/sessions/{session.id}/complete")

        assert session.need == "done"

    async def test_complete_clears_pending_result(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """The pending result is consumed (cleared) once approved."""
        session, _ = await _drive_session_to_approve(session_service)

        client.post(f"/api/sessions/{session.id}/complete")

        assert session.pending_result is None

    async def test_complete_resolves_the_handler_future(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """handler.complete() resolves the underlying asyncio.Future."""
        session, expected_result = await _drive_session_to_approve(
            session_service,
        )

        client.post(f"/api/sessions/{session.id}/complete")

        assert session.handler.done()
        assert session.handler.result() == expected_result

    async def test_complete_records_memory(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """handler.complete() writes an episode to configured memories."""
        mock_memory = AsyncMock(spec=Memory)
        mock_memory.recall.return_value = ""
        session, _ = await _drive_session_to_approve(
            session_service,
            memories=[mock_memory],
        )

        client.post(f"/api/sessions/{session.id}/complete")

        mock_memory.record.assert_awaited_once()

    async def test_complete_second_call_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Calling complete twice: the second call 409s (need is now done)."""
        session, _ = await _drive_session_to_approve(session_service)

        first = client.post(f"/api/sessions/{session.id}/complete")
        second = client.post(f"/api/sessions/{session.id}/complete")

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_409_CONFLICT

    async def test_complete_wrong_need_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A session not at need='approve' (still 'next') 409s."""
        llm = AsyncMock()
        agent = LLMAgent(llm=llm)
        task = Task(instruction="do something")
        handler = await agent.run_supervised(task)
        session = session_service.create_session(agent=agent, handler=handler)

        response = client.post(f"/api/sessions/{session.id}/complete")

        assert response.status_code == status.HTTP_409_CONFLICT

    async def test_complete_unknown_session_returns_404(
        self,
        client: TestClient,
    ) -> None:
        """An unknown session id 404s."""
        response = client.post("/api/sessions/sess_does-not-exist/complete")

        assert response.status_code == status.HTTP_404_NOT_FOUND
