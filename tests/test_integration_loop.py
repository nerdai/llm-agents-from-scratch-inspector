"""End-to-end integration test for the M1 supervised loop.

Unlike the per-issue test files (each written in isolation by a
different contributor against #3/#4/#5/#6 separately), this test
drives the *actual* HTTP routes for the full Hailstone-from-4 TRD
example end to end: next-step -> run-step -> next-step -> run-step ->
next-step -> complete. It exists specifically to prove the
reconciliation between those four issues' independently-added
``Session`` fields (``pending_step``, ``pending_result``,
``last_step_result``) actually wires the loop together correctly, not
just that each route works in isolation against a hand-built
``Session``.

No live Ollama daemon is used: the backbone LLM is a scripted,
network-free ``BaseLLM`` that returns a fixed sequence of responses,
mirroring the pattern already used in ``test_next_step_route.py`` /
``test_run_step_route.py`` / ``llm-agents-from-scratch``'s own test
suite.
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
    ToolCall,
    ToolCallResult,
)
from llm_agents_from_scratch.tools.simple_function import SimpleFunctionTool

from agent_inspector.deps import get_session_service
from agent_inspector.server import create_app
from agent_inspector.services.session import SessionService

_HTTP_OK = 200
_HTTP_CONFLICT = 409


def next_number(x: int) -> int:
    """The Hailstone-sequence step function (mirrors services.py's own)."""
    return x // 2 if x % 2 == 0 else 3 * x + 1


class _SequencedLLM(BaseLLM):
    """A scripted ``BaseLLM`` that plays back a fixed call sequence.

    ``chat()``/``continue_chat_with_tool_results()`` calls consume from
    ``tool_turns`` in order (one entry per ``run_step`` call);
    ``structured_output()`` calls consume from ``decisions`` in order
    (one entry per LLM-routed ``get_next_step`` call -- the
    deterministic first call never reaches the LLM at all).
    """

    def __init__(
        self,
        tool_turns: list[tuple[ToolCall | None, str]],
        decisions: list[NextStepDecision],
    ) -> None:
        self._tool_turns = list(tool_turns)
        self._decisions = list(decisions)

    async def complete(self, prompt: str, **kwargs: Any) -> CompleteResult:
        """Unused on this test's path; provided to satisfy BaseLLM."""
        raise NotImplementedError

    async def structured_output(
        self,
        prompt: str,
        mdl: type[StructuredOutputType],
        **kwargs: Any,
    ) -> StructuredOutputType:
        """Return the next scripted ``NextStepDecision``."""
        return self._decisions.pop(0)  # type: ignore[return-value]

    async def chat(
        self,
        input: str,
        chat_history: Sequence[ChatMessage] | None = None,
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[ChatMessage, ChatMessage]:
        """Decide (per the script) whether to call a tool this turn."""
        tool_call, _ = self._tool_turns[0]
        tool_calls = [tool_call] if tool_call else None
        return (
            ChatMessage(role=ChatRole.USER, content=input),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content="Calling a tool." if tool_calls else "Done.",
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
        """Return this turn's scripted final content, then advance."""
        _, final_content = self._tool_turns.pop(0)
        return (
            [
                ChatMessage(role=ChatRole.TOOL, content=str(r.content))
                for r in tool_call_results
            ],
            ChatMessage(role=ChatRole.ASSISTANT, content=final_content),
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


class TestHailstoneFromFourEndToEnd:
    """Drives the full TRD example loop through the real HTTP routes."""

    async def test_full_loop_reaches_done(  # noqa: PLR0915
        self,
        client: TestClient,
        session_service: SessionService,
    ) -> None:
        """4 -> 2 -> 1, approved, matches the TRD's worked example.

        Deliberately one long linear walkthrough rather than split
        across smaller tests: each step's assertions depend on the
        session's state after the previous one, so splitting would
        mean either re-deriving that state per test (duplicated setup
        that could silently drift from the real sequence) or chaining
        fixtures in a way that's harder to read than the loop's own
        chronology.
        """
        llm = _SequencedLLM(
            tool_turns=[
                (
                    ToolCall(tool_name="next_number", arguments={"x": 4}),
                    "4 is even, so the next number is 2.",
                ),
                (
                    ToolCall(tool_name="next_number", arguments={"x": 2}),
                    "2 is even, so the next number is 1.",
                ),
            ],
            decisions=[
                NextStepDecision(
                    kind="next_step",
                    content="Call next_number with x=2.",
                ),
                NextStepDecision(kind="final_result", content=""),
            ],
        )
        agent = LLMAgent(llm=llm, tools=[SimpleFunctionTool(next_number)])
        task = Task(
            instruction=(
                "Compute the Hailstone sequence starting from 4 until "
                "you reach 1."
            ),
        )
        handler = await agent.run_supervised(task)
        session = session_service.create_session(agent=agent, handler=handler)

        # 1. next-step: first call, deterministic, no LLM consulted.
        r1 = client.post(f"/api/sessions/{session.id}/next-step")
        assert r1.status_code == _HTTP_OK
        b1 = r1.json()
        assert b1["kind"] == "next_step"
        assert b1["need"] == "run"
        assert session.pending_step is not None
        assert session.need == "run"

        # A run-step call is now valid; a next-step call is not (busy phase).
        assert (
            client.post(f"/api/sessions/{session.id}/next-step").status_code
            == _HTTP_CONFLICT
        )

        # 2. run-step: executes next_number(4) for real -> 2.
        r2 = client.post(f"/api/sessions/{session.id}/run-step")
        assert r2.status_code == _HTTP_OK
        b2 = r2.json()
        assert b2["need"] == "next"
        assert b2["tool_calls"] == [
            {
                "tool_name": "next_number",
                "args": {"x": 4},
                "content": "2",
                "error": False,
            },
        ]
        assert b2["step_counter"] == 1
        assert session.pending_step is None
        assert session.last_step_result is not None

        # 3. next-step: LLM-routed, decides to continue.
        r3 = client.post(f"/api/sessions/{session.id}/next-step")
        assert r3.status_code == _HTTP_OK
        b3 = r3.json()
        assert b3["kind"] == "next_step"
        assert b3["need"] == "run"
        assert b3["step"]["instruction"] == "Call next_number with x=2."
        assert session.pending_step is not None

        # 4. run-step: executes next_number(2) for real -> 1.
        r4 = client.post(f"/api/sessions/{session.id}/run-step")
        assert r4.status_code == _HTTP_OK
        b4 = r4.json()
        assert b4["need"] == "next"
        assert b4["tool_calls"] == [
            {
                "tool_name": "next_number",
                "args": {"x": 2},
                "content": "1",
                "error": False,
            },
        ]
        assert b4["step_counter"] == 2  # noqa: PLR2004

        # 5. next-step: LLM-routed, decides the task is done.
        r5 = client.post(f"/api/sessions/{session.id}/next-step")
        assert r5.status_code == _HTTP_OK
        b5 = r5.json()
        assert b5["kind"] == "final_result"
        assert b5["need"] == "approve"
        assert isinstance(b5["result"]["content"], str)
        assert b5["result"]["content"]
        assert session.pending_result is not None
        assert session.need == "approve"

        # A run-step call is not valid at the approval gate.
        assert (
            client.post(f"/api/sessions/{session.id}/run-step").status_code
            == _HTTP_CONFLICT
        )

        # 6. complete: operator approves, handler resolves.
        r6 = client.post(f"/api/sessions/{session.id}/complete")
        assert r6.status_code == _HTTP_OK
        b6 = r6.json()
        assert b6["status"] == "resolved"
        assert b6["need"] == "done"
        assert session.need == "done"
        assert session.pending_result is None
        assert handler.done()
        assert handler.result().content == b6["result"]["content"]

        # The loop is over: nothing further is valid on this session.
        assert (
            client.post(f"/api/sessions/{session.id}/complete").status_code
            == _HTTP_CONFLICT
        )
        assert (
            client.post(f"/api/sessions/{session.id}/next-step").status_code
            == _HTTP_CONFLICT
        )
