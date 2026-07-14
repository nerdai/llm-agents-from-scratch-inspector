"""Tests for ``PATCH /api/sessions/{id}/step`` (issue #13).

Exercises the route end-to-end through a real ``LLMAgent`` +
``SupervisedTaskHandler``, mirroring the fixture/mocking pattern used
in ``tests/test_run_step_route.py``: a network-free but otherwise real
``BaseLLM`` stand-in drives the framework's own tool-calling loop, so
these tests also prove the edited instruction is what ``run-step``
(#5) actually executes -- not just that the session's in-memory state
was mutated.
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

    Mirrors ``tests/test_run_step_route.py::_ScriptedLLM``, plus
    records every ``chat()`` call's ``input`` so tests can assert on
    exactly what instruction text ``run_step`` fed the LLM.
    """

    def __init__(
        self,
        tool_call: ToolCall | None,
        final_content: str = "The next number is 5.",
    ) -> None:
        self._tool_call = tool_call
        self._final_content = final_content
        self.chat_inputs: list[str] = []

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
        self.chat_inputs.append(input)
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
    with_pending_step: bool = True,
) -> tuple[Session, TaskStep | None]:
    """Build a Session with a real LLMAgent + SupervisedTaskHandler.

    Mirrors ``tests/test_run_step_route.py::_build_session``: registers
    the ``next_number`` tool, and -- unless ``with_pending_step`` is
    ``False`` -- obtains a pending ``TaskStep`` via
    ``handler.get_next_step(None)`` (no LLM call needed for the first
    step) and stashes it on the session the way #4's next-step
    endpoint is expected to.

    Returns:
        tuple[Session, TaskStep | None]: The created session and the
            ``TaskStep`` set as ``pending_step`` (``None`` if
            ``with_pending_step`` is ``False``).
    """
    agent = LLMAgent(llm=llm, tools=[SimpleFunctionTool(next_number)])
    task = Task(instruction="Figure out the next number after 4.")
    handler = await agent.run_supervised(task)

    session = session_service.create_session(agent=agent, handler=handler)

    step: TaskStep | None = None
    if with_pending_step:
        step = await handler.get_next_step(None)
        assert isinstance(step, TaskStep)
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


class TestPatchStepSuccess:
    """Happy path: in-place instruction edit, ``need`` untouched."""

    async def test_edit_step_updates_instruction(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """The edited instruction persists on ``pending_step`` and is echoed."""
        llm = _ScriptedLLM(tool_call=None)
        session, step = await _build_session(session_service, llm)
        assert step is not None
        original_instruction = step.instruction

        new_instruction = "Call the next_number tool with x=4. (edited)"
        response = client.patch(
            f"/api/sessions/{session.id}/step",
            json={"instruction": new_instruction},
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["edited"] is True
        assert body["need"] == "run"
        assert body["step"]["instruction"] == new_instruction
        assert body["step"]["instruction"] != original_instruction
        assert body["step"]["id_"] == step.id_
        assert body["step"]["task_id"] == step.task_id

        # Persisted on the session's pending step, not just echoed back.
        assert session.pending_step is not None
        assert session.pending_step.instruction == new_instruction
        assert session.need == "run"

    async def test_edit_step_does_not_touch_pending_result_or_last_step_result(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Editing a pending step leaves the other session fields alone."""
        llm = _ScriptedLLM(tool_call=None)
        session, _ = await _build_session(session_service, llm)
        assert session.pending_result is None
        assert session.last_step_result is None

        response = client.patch(
            f"/api/sessions/{session.id}/step",
            json={"instruction": "something else entirely"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert session.pending_result is None
        assert session.last_step_result is None

    async def test_edited_instruction_is_what_run_step_executes(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """The edit propagates: run-step executes the *edited* instruction.

        Per the issue's verified framework behavior, ``run_step()``
        reads ``step.instruction`` fresh at call time rather than off
        an earlier snapshot, so editing while ``need == "run"`` (i.e.
        strictly before run-step consumes the step) is correctly
        picked up.
        """
        tool_call = ToolCall(tool_name="next_number", arguments={"x": 4})
        llm = _ScriptedLLM(tool_call=tool_call, final_content="It's 5.")
        session, step = await _build_session(session_service, llm)
        assert step is not None
        original_instruction = step.instruction

        edited_instruction = "Call the next_number tool with x=4. (edited)"
        edit_response = client.patch(
            f"/api/sessions/{session.id}/step",
            json={"instruction": edited_instruction},
        )
        assert edit_response.status_code == status.HTTP_200_OK

        run_response = client.post(f"/api/sessions/{session.id}/run-step")

        assert run_response.status_code == status.HTTP_200_OK
        assert len(llm.chat_inputs) == 1
        executed_input = llm.chat_inputs[0]
        assert edited_instruction in executed_input
        assert original_instruction not in executed_input


class TestPatchStepWrongNeed:
    """409 when ``need != 'run'``."""

    async def test_edit_step_wrong_need_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A session not waiting on 'run' rejects the edit with 409."""
        llm = _ScriptedLLM(tool_call=None)
        session, _ = await _build_session(
            session_service,
            llm,
            need="next",
            with_pending_step=False,
        )

        response = client.patch(
            f"/api/sessions/{session.id}/step",
            json={"instruction": "new instruction"},
        )

        assert response.status_code == status.HTTP_409_CONFLICT

    async def test_edit_step_wrong_need_does_not_mutate(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A rejected edit leaves the session's pending step untouched."""
        llm = _ScriptedLLM(tool_call=None)
        session, _ = await _build_session(
            session_service,
            llm,
            need="approve",
            with_pending_step=False,
        )

        response = client.patch(
            f"/api/sessions/{session.id}/step",
            json={"instruction": "new instruction"},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert session.pending_step is None
        assert session.need == "approve"


class TestPatchStepNotFound:
    """404 for an unknown session id."""

    def test_edit_step_unknown_session_returns_404(
        self,
        client: TestClient,
    ) -> None:
        """A bogus session id returns 404."""
        response = client.patch(
            "/api/sessions/sess_does-not-exist/step",
            json={"instruction": "new instruction"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPatchStepBusy:
    """409 when the session already has a call in flight."""

    async def test_edit_step_busy_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A concurrent call holding the session's lock blocks the edit."""
        llm = _ScriptedLLM(tool_call=None)
        session, _ = await _build_session(session_service, llm)

        lock_cm = session_service.lock_session(session.id)
        lock_cm.__enter__()
        try:
            response = client.patch(
                f"/api/sessions/{session.id}/step",
                json={"instruction": "new instruction"},
            )
            assert response.status_code == status.HTTP_409_CONFLICT
        finally:
            lock_cm.__exit__(None, None, None)


class TestPatchStepValidation:
    """422 for a malformed request body."""

    async def test_edit_step_empty_instruction_returns_422(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """An empty instruction is rejected before hitting the service."""
        llm = _ScriptedLLM(tool_call=None)
        session, _ = await _build_session(session_service, llm)

        response = client.patch(
            f"/api/sessions/{session.id}/step",
            json={"instruction": ""},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        # Unmutated: validation failed before the service was called.
        assert session.pending_step is not None
