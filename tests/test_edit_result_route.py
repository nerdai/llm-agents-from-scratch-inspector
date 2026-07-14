"""Tests for ``PATCH /api/sessions/{id}/result`` (TRD §6.11, issue #14).

Drives a real ``LLMAgent`` + ``SupervisedTaskHandler`` through a real
``run_step()`` call (mirroring ``tests/test_run_step_route.py``'s
mocking pattern) to reach ``need == "next"`` with a real
``last_step_result`` and a real, non-trivial ``handler.rollout`` -- so
these tests prove the span-tracking bookkeeping added to
``SessionService.run_step`` actually lets ``edit_result`` splice
edited content into ``rollout`` at exactly the right place, not just
that *a* change happened somewhere in the string.
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

    Same pattern as ``tests/test_run_step_route.py``'s ``_ScriptedLLM``
    -- a concrete ``BaseLLM`` subclass rather than mocking ``run_step``
    itself, so the real tool-calling loop inside ``run_step`` (and the
    real ``rollout`` append it performs) actually runs.
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


async def _build_session_at_next(
    session_service: SessionService,
    llm: BaseLLM,
) -> Session:
    """Build a session parked at ``need == "next"`` via a real run-step.

    Registers the ``next_number`` tool, obtains the first pending
    ``TaskStep`` via ``handler.get_next_step(None)``, and runs it for
    real through ``SessionService.run_step`` -- so ``last_step_result``
    and ``last_rollout_span`` are populated exactly the way the real
    ``run-step`` route (#5) would leave them.
    """
    agent = LLMAgent(llm=llm, tools=[SimpleFunctionTool(next_number)])
    task = Task(instruction="Figure out the next number after 4.")
    handler = await agent.run_supervised(task)
    step = await handler.get_next_step(None)
    assert isinstance(step, TaskStep)

    session = session_service.create_session(agent=agent, handler=handler)
    session.pending_step = step
    session.need = "run"  # type: ignore[assignment]

    await session_service.run_step(session)
    assert session.need == "next"
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


class TestEditResultSuccess:
    """Happy path: content and rollout both reflect the edit."""

    async def test_edit_persists_content_and_rollout(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """The edit lands on last_step_result.content and in rollout.

        Also asserts the edited text replaces exactly the span
        ``run_step`` recorded, not the whole rollout and not some
        other location.
        """
        tool_call = ToolCall(tool_name="next_number", arguments={"x": 4})
        llm = _ScriptedLLM(tool_call=tool_call, final_content="It's 5.")
        session = await _build_session_at_next(session_service, llm)

        rollout_before = session.handler.rollout
        assert "It's 5." in rollout_before
        # Sanity check on the fixture: run_step actually appended a
        # non-trivial, multi-line formatted block, not just the raw
        # content string.
        assert "=== Task Step Start ===" in rollout_before
        span_before = session.last_rollout_span
        assert span_before is not None
        start, end = span_before
        assert rollout_before[start:end] == rollout_before[start:]
        assert "It's 5." in rollout_before[start:end]

        edited = "The next number after 4 is 2. Continue with x=2."
        response = client.patch(
            f"/api/sessions/{session.id}/result",
            json={"content": edited},
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["result"]["content"] == edited
        assert body["edited"] is True
        assert body["need"] == "next"

        # The service-level object is mutated in place.
        assert session.last_step_result.content == edited

        # The rollout now contains the edited text at exactly the
        # recorded span, with everything before/after the span left
        # untouched (not duplicated, not clobbering an adjacent span).
        expected_rollout = (
            rollout_before[:start] + edited + rollout_before[end:]
        )
        assert session.handler.rollout == expected_rollout
        assert session.handler.rollout.count(edited) == 1
        # The un-edited framework formatting for this step is gone --
        # replaced by the edit, not left behind alongside it.
        assert "It's 5." not in session.handler.rollout
        assert "=== Task Step Start ===" not in session.handler.rollout

        # Span bookkeeping is updated to match the new content length.
        new_start, new_end = session.last_rollout_span
        assert new_start == start
        assert new_end == start + len(edited)

    async def test_second_edit_after_second_run_step(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Span tracking survives a length-changing edit + another run-step.

        Edits step 1's result to a *different length* than the
        original, then drives a second real ``run_step``, then edits
        step 2's result -- proving the recorded span for step 2 (and
        the edit to it) targets the right place even though step 1's
        edit shifted everything after it.
        """
        tool_call_1 = ToolCall(tool_name="next_number", arguments={"x": 4})
        llm = _ScriptedLLM(tool_call=tool_call_1, final_content="Step one.")
        session = await _build_session_at_next(session_service, llm)

        first_span = session.last_rollout_span
        assert first_span is not None
        first_start, first_end = first_span
        rollout_after_step_1 = session.handler.rollout

        # Edit step 1's result to a much longer string than the
        # original -- this shifts every later offset in `rollout`.
        long_edit = "A" * 200 + " (edited, much longer than the original)"
        edit_response = client.patch(
            f"/api/sessions/{session.id}/result",
            json={"content": long_edit},
        )
        assert edit_response.status_code == status.HTTP_200_OK

        rollout_after_edit = session.handler.rollout
        assert rollout_after_edit == (
            rollout_after_step_1[:first_start]
            + long_edit
            + rollout_after_step_1[first_end:]
        )
        updated_span = session.last_rollout_span
        assert updated_span == (first_start, first_start + len(long_edit))

        # Drive a second, real run-step (need -> "run" -> "next" again).
        session.pending_step = TaskStep(
            task_id=session.handler.task.id_,
            instruction="one more step",
        )
        session.need = "run"  # type: ignore[assignment]
        # Swap in an LLM that produces a distinct second step result
        # (still via a tool call, so `_final_content` is actually used
        # -- see `_ScriptedLLM.chat`'s hardcoded "Done." for the
        # no-tool-call path).
        session.agent.llm._tool_call = ToolCall(
            tool_name="next_number",
            arguments={"x": 1},
        )
        session.agent.llm._final_content = "Step two."

        run_step_response = client.post(f"/api/sessions/{session.id}/run-step")
        assert run_step_response.status_code == status.HTTP_200_OK
        assert run_step_response.json()["result"]["content"] == "Step two."

        second_span = session.last_rollout_span
        assert second_span is not None
        second_start, second_end = second_span
        # The second step's span must start where the (now-edited)
        # first step's content ended, *plus* the "\n\n" separator the
        # framework prepends before a non-first step's formatted text
        # -- i.e. bookkeeping wasn't corrupted by the earlier,
        # length-changing edit, and the separator itself is excluded
        # from the span so a later edit can't swallow it.
        rollout_joiner_len = 2
        assert second_start == first_start + len(long_edit) + rollout_joiner_len
        rollout_after_step_2 = session.handler.rollout
        assert rollout_after_step_2[:second_start] == (
            rollout_after_edit + "\n\n"
        )
        assert "Step two." in rollout_after_step_2[second_start:second_end]

        # Now edit step 2's result and confirm it lands precisely,
        # leaving step 1's already-edited text completely untouched.
        second_edit = "Second step, edited."
        second_edit_response = client.patch(
            f"/api/sessions/{session.id}/result",
            json={"content": second_edit},
        )
        assert second_edit_response.status_code == status.HTTP_200_OK

        final_rollout = session.handler.rollout
        assert final_rollout == (
            rollout_after_step_2[:second_start]
            + second_edit
            + rollout_after_step_2[second_end:]
        )
        # Step 1's edited content, preceding the second step, is
        # unaffected by editing step 2 -- and the "\n\n" separator
        # between the two steps survived the edit rather than being
        # swallowed by it (the separator is excluded from the
        # recorded span precisely so this holds).
        assert final_rollout[:second_start] == rollout_after_edit + "\n\n"
        assert f"{long_edit}\n\n{second_edit}" in final_rollout
        assert long_edit in final_rollout
        assert session.last_step_result.content == second_edit


class TestEditResultInvalidSpan:
    """500 when ``last_rollout_span`` is missing or out of bounds.

    Both are server-side invariant violations, not client errors:
    ``run_step`` always sets a span consistent with the ``rollout`` it
    just wrote. An out-of-bounds span is deliberately tested here
    because Python slicing never raises on one -- it would otherwise
    splice silently wrong instead of surfacing as an error.
    """

    async def test_out_of_bounds_span_raises_instead_of_corrupting(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A stale/invalid span 500s instead of silently mis-splicing."""
        tool_call = ToolCall(tool_name="next_number", arguments={"x": 4})
        llm = _ScriptedLLM(tool_call=tool_call, final_content="It's 5.")
        session = await _build_session_at_next(session_service, llm)
        rollout_before = session.handler.rollout

        # Simulate a corrupted/stale span: end far beyond the actual
        # rollout length.
        session.last_rollout_span = (0, len(rollout_before) + 1000)

        response = client.patch(
            f"/api/sessions/{session.id}/result",
            json={"content": "whatever"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        # The rollout must be left untouched -- no silently-wrong splice.
        assert session.handler.rollout == rollout_before

    async def test_inverted_span_raises_instead_of_corrupting(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A span with start > end 500s instead of an empty/reversed splice."""
        tool_call = ToolCall(tool_name="next_number", arguments={"x": 4})
        llm = _ScriptedLLM(tool_call=tool_call, final_content="It's 5.")
        session = await _build_session_at_next(session_service, llm)
        rollout_before = session.handler.rollout
        assert session.last_rollout_span is not None
        start, end = session.last_rollout_span

        session.last_rollout_span = (end, start)  # inverted

        response = client.patch(
            f"/api/sessions/{session.id}/result",
            json={"content": "whatever"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert session.handler.rollout == rollout_before


class TestEditResultWrongNeed:
    """409 when need != 'next'."""

    async def test_edit_wrong_need_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A session at need='run' rejects the edit with 409."""
        llm = _ScriptedLLM(tool_call=None)
        agent = LLMAgent(llm=llm, tools=[SimpleFunctionTool(next_number)])
        task = Task(instruction="Figure out the next number after 4.")
        handler = await agent.run_supervised(task)
        step = await handler.get_next_step(None)
        session = session_service.create_session(agent=agent, handler=handler)
        session.pending_step = step
        session.need = "run"  # type: ignore[assignment]

        response = client.patch(
            f"/api/sessions/{session.id}/result",
            json={"content": "whatever"},
        )

        assert response.status_code == status.HTTP_409_CONFLICT

    async def test_edit_fresh_session_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """A brand-new session (need='next', no run-step yet) is 409.

        need == "next" holds right after session creation too, but
        there's no TaskStepResult yet to edit.
        """
        llm = _ScriptedLLM(tool_call=None)
        agent = LLMAgent(llm=llm, tools=[SimpleFunctionTool(next_number)])
        task = Task(instruction="Figure out the next number after 4.")
        handler = await agent.run_supervised(task)
        session = session_service.create_session(agent=agent, handler=handler)
        assert session.need == "next"

        response = client.patch(
            f"/api/sessions/{session.id}/result",
            json={"content": "whatever"},
        )

        assert response.status_code == status.HTTP_409_CONFLICT


class TestEditResultNotFound:
    """404 for an unknown session id."""

    def test_edit_unknown_session_returns_404(
        self,
        client: TestClient,
    ) -> None:
        """A bogus session id returns 404."""
        response = client.patch(
            "/api/sessions/sess_does-not-exist/result",
            json={"content": "whatever"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestEditResultBusy:
    """409 when the session already has a call in flight."""

    async def test_edit_busy_session_returns_409(
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """Holding the busy lock externally makes the edit 409."""
        tool_call = ToolCall(tool_name="next_number", arguments={"x": 4})
        llm = _ScriptedLLM(tool_call=tool_call)
        session = await _build_session_at_next(session_service, llm)

        with session_service.lock_session(session.id):
            response = client.patch(
                f"/api/sessions/{session.id}/result",
                json={"content": "whatever"},
            )

        assert response.status_code == status.HTTP_409_CONFLICT
