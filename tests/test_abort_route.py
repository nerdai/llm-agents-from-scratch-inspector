"""Tests for ``POST /api/sessions/{id}/abort`` (TRD §6.6, issue #12).

Drives a real ``LLMAgent`` + ``SupervisedTaskHandler`` into each
non-terminal ``need`` and exercises the route via FastAPI's
``TestClient``. Mocks the LLM's network call the same way
``test_complete_route.py`` does (``AsyncMock`` on ``structured_output``),
so no real Ollama call is made.
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


async def _new_session(
    session_service: SessionService,
    *,
    memories: list[Memory] | None = None,
) -> Session:
    """Build a session parked at ``need == "next"`` (freshly created).

    Args:
        session_service (SessionService): The service to register the
            session on.
        memories (list[Memory] | None): Memories to attach to the
            agent, if any.

    Returns:
        Session: The newly created, stored session.
    """
    llm = AsyncMock()
    agent = LLMAgent(llm=llm, memories=memories or [])
    task = Task(instruction="do something")
    handler = await agent.run_supervised(task)
    return session_service.create_session(agent=agent, handler=handler)


async def _drive_session_to_run(
    session_service: SessionService,
) -> tuple[Session, TaskStep]:
    """Build a session parked at ``need == "run"`` with a pending step.

    ``handler.get_next_step(None)`` is the deterministic first-call
    path (wraps the task instruction, no LLM call), so an unconfigured
    ``AsyncMock`` LLM is sufficient here.

    Args:
        session_service (SessionService): The service to register the
            session on.

    Returns:
        tuple[Session, TaskStep]: The registered session (already
            transitioned to ``need="run"`` with ``pending_step`` set)
            and the ``TaskStep`` it holds.
    """
    llm = AsyncMock()
    agent = LLMAgent(llm=llm)
    task = Task(instruction="do something")
    handler = await agent.run_supervised(task)

    step = await handler.get_next_step(None)
    assert isinstance(step, TaskStep)

    session = session_service.create_session(agent=agent, handler=handler)
    session.pending_step = step
    session_service.transition_need(session, "run")
    return session, step


async def _drive_session_to_approve(
    session_service: SessionService,
) -> tuple[Session, TaskResult]:
    """Build a session parked at ``need == "approve"`` with a pending result.

    Mocks the LLM's ``structured_output`` call to immediately decide
    ``final_result``, so no real LLM/Ollama call is made -- mirrors
    ``test_complete_route.py``'s helper of the same name.

    Args:
        session_service (SessionService): The service to register the
            session on.

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


class TestPostAbort:
    """``POST /api/sessions/{id}/abort`` (TRD §6.6)."""

    async def test_abort_from_next_returns_aborted_status_and_done_need(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Abort from need='next': 200 with aborted status, need=done."""
        session = await _new_session(session_service)

        response = client.post(f"/api/sessions/{session.id}/abort")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "aborted", "need": "done"}
        assert session.need == "done"

    async def test_abort_from_next_resolves_handler_with_exception(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """abort() resolves the handler's future with an exception."""
        session = await _new_session(session_service)

        client.post(f"/api/sessions/{session.id}/abort")

        assert session.handler.done()
        assert session.handler.exception() is not None

    async def test_abort_records_memory(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """handler.abort() writes an episode to configured memories.

        Guards the ``await session.handler.abort()`` call in
        ``SessionService.abort`` -- mirrors
        ``test_complete_route.py::test_complete_records_memory``.
        """
        mock_memory = AsyncMock(spec=Memory)
        mock_memory.recall.return_value = ""
        session = await _new_session(session_service, memories=[mock_memory])

        client.post(f"/api/sessions/{session.id}/abort")

        mock_memory.record.assert_awaited_once()

    async def test_abort_from_run_clears_pending_step(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Abort from need='run': pending_step is cleared, need=done."""
        session, _ = await _drive_session_to_run(session_service)

        response = client.post(f"/api/sessions/{session.id}/abort")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "aborted", "need": "done"}
        assert session.need == "done"
        assert session.pending_step is None
        assert session.handler.done()
        assert session.handler.exception() is not None

    async def test_abort_from_approve_clears_pending_result(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Abort from need='approve': pending_result is cleared, need=done."""
        session, _ = await _drive_session_to_approve(session_service)

        response = client.post(f"/api/sessions/{session.id}/abort")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "aborted", "need": "done"}
        assert session.need == "done"
        assert session.pending_result is None
        assert session.handler.done()
        assert session.handler.exception() is not None

    async def test_abort_already_done_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Aborting an already-done session 409s."""
        session = await _new_session(session_service)

        first = client.post(f"/api/sessions/{session.id}/abort")
        second = client.post(f"/api/sessions/{session.id}/abort")

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_409_CONFLICT

    async def test_abort_unknown_session_returns_404(
        self,
        client: TestClient,
    ) -> None:
        """An unknown session id 404s."""
        response = client.post("/api/sessions/sess_does-not-exist/abort")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_abort_busy_session_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A session with another mutating call already in flight 409s."""
        session = await _new_session(session_service)

        with session_service.lock_session(session.id):
            response = client.post(f"/api/sessions/{session.id}/abort")

        assert response.status_code == status.HTTP_409_CONFLICT
