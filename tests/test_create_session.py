"""Tests for session creation (issue #3, reworked by #47/ADR-002).

Covers both layers:
    * ``SessionService.create_session_from_config`` -- the business
      logic that calls the configured ``LLMAgentBuilder.build()`` and
      ``run_supervised()``, and registers the session.
    * ``POST /api/sessions`` -- the thin route wrapping it, including
      the request/response shape and the ``422`` on invalid config.

Per ADR-002, sessions are no longer built from HTTP config
(``model``/``think``/``function_tools``): they're built by calling
``.build()`` on an ``LLMAgentBuilder`` that ``agent-inspector launch
<script>`` would have discovered from the user's own script. Tests
here stand in for that discovered builder with a fixture
``LLMAgentBuilder`` wired to a network-free ``BaseLLM``, following the
same pattern as ``test_next_step_route.py``'s ``_MockBaseLLM``, and
inject it into ``SessionService`` directly (the same role
``deps.configure_agent_builder`` plays at real CLI-launch time).
"""

from typing import Any, Sequence
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from llm_agents_from_scratch import LLMAgent, LLMAgentBuilder
from llm_agents_from_scratch.base.llm import BaseLLM, StructuredOutputType
from llm_agents_from_scratch.base.tool import Tool
from llm_agents_from_scratch.data_structures import (
    ChatMessage,
    ChatRole,
    CompleteResult,
    NextStepDecision,
    ToolCallResult,
)

from agent_inspector.deps import get_session_service
from agent_inspector.errors.session import (
    AgentBuilderNotConfiguredError,
    AgentBuildError,
    SessionConfigError,
)
from agent_inspector.server import create_app
from agent_inspector.services.session import SessionService

_HAILSTONE_TASK = "Compute the full Hailstone sequence starting from 4."


class _MockBaseLLM(BaseLLM):
    """Network-free ``BaseLLM`` stand-in, mirroring the pattern used in
    ``test_next_step_route.py``.

    Only ``structured_output`` -- the call ``SupervisedTaskHandler.
    get_next_step`` makes -- matters for these tests; the rest is
    implemented purely to satisfy ``BaseLLM``'s abstract interface.
    """

    async def complete(self, prompt: str, **kwargs: Any) -> CompleteResult:
        """Unused here; provided to satisfy BaseLLM."""
        return CompleteResult(response="mock complete", prompt=prompt)

    async def structured_output(
        self,
        prompt: str,
        mdl: type[StructuredOutputType],
        **kwargs: Any,
    ) -> StructuredOutputType:
        """Unused on the create-session path; provided to satisfy BaseLLM."""
        return NextStepDecision(  # type: ignore[return-value]
            kind="final_result",
            content="",
        )

    async def chat(
        self,
        input: str,
        chat_history: Sequence[ChatMessage] | None = None,
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[ChatMessage, ChatMessage]:
        """Unused here; provided to satisfy BaseLLM."""
        return (
            ChatMessage(role=ChatRole.USER, content=input),
            ChatMessage(role=ChatRole.ASSISTANT, content="mock chat response"),
        )

    async def continue_chat_with_tool_results(
        self,
        tool_call_results: Sequence[ToolCallResult],
        chat_history: Sequence[ChatMessage],
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[list[ChatMessage], ChatMessage]:
        """Unused here; provided to satisfy BaseLLM."""
        return ([], ChatMessage(role=ChatRole.ASSISTANT, content="mock tool"))


@pytest.fixture
def agent_builder() -> LLMAgentBuilder:
    """A fixture ``LLMAgentBuilder`` standing in for a discovered one."""
    return LLMAgentBuilder(llm=_MockBaseLLM())


class TestCreateSessionFromConfig:
    """``SessionService.create_session_from_config`` (service layer)."""

    async def test_builds_agent_via_configured_builder(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """The agent is whatever the configured builder's build() returns."""
        service = SessionService(agent_builder=agent_builder)

        session = await service.create_session_from_config(task=_HAILSTONE_TASK)

        assert isinstance(session.agent, LLMAgent)
        assert session.agent.llm is agent_builder.llm

    async def test_calls_build_once_per_session(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """Each new session gets its own, independently-built LLMAgent."""
        service = SessionService(agent_builder=agent_builder)

        first = await service.create_session_from_config(task="task one")
        second = await service.create_session_from_config(task="task two")

        assert first.agent is not second.agent

    async def test_starts_supervised_handler_at_need_next(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A freshly created session's handler is seeded from ``task``."""
        service = SessionService(agent_builder=agent_builder)

        session = await service.create_session_from_config(task=_HAILSTONE_TASK)

        assert session.need == "next"
        assert session.id.startswith("sess_")
        assert session.handler.task.instruction == _HAILSTONE_TASK
        assert session.handler.task.id_

    async def test_registered_session_is_retrievable(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """The returned session is the one stored in the registry."""
        service = SessionService(agent_builder=agent_builder)

        session = await service.create_session_from_config(task="do a thing")

        assert service.get_session(session.id) is session

    @pytest.mark.parametrize("blank_task", ["", "   ", "\n\t"])
    async def test_blank_task_raises_session_config_error(
        self,
        agent_builder: LLMAgentBuilder,
        blank_task: str,
    ) -> None:
        """A blank (or whitespace-only) task is rejected as bad config."""
        service = SessionService(agent_builder=agent_builder)

        with pytest.raises(SessionConfigError):
            await service.create_session_from_config(task=blank_task)

    async def test_no_configured_builder_raises(self) -> None:
        """No ``agent_builder`` wired up -> a clear domain error, not a crash"""
        service = SessionService()

        with pytest.raises(AgentBuilderNotConfiguredError):
            await service.create_session_from_config(task="do a thing")

    async def test_builder_build_failure_is_wrapped(self) -> None:
        """A failure inside the builder's own ``build()`` is wrapped."""
        broken_builder = AsyncMock(spec=LLMAgentBuilder)
        broken_builder.build.side_effect = RuntimeError("mcp unreachable")
        service = SessionService(agent_builder=broken_builder)

        with pytest.raises(AgentBuildError):
            await service.create_session_from_config(task="do a thing")


def _client(session_service: SessionService) -> TestClient:
    """Build a ``TestClient`` wired to ``session_service`` via dep override."""
    app = create_app(serve_static=False)
    app.dependency_overrides[get_session_service] = lambda: session_service
    return TestClient(app)


class TestCreateSessionRoute:
    """``POST /api/sessions`` (route layer, TRD §6.1)."""

    def test_returns_expected_response_shape(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A well-formed request gets back the TRD §6.1 response shape."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post(
            "/api/sessions",
            json={"task": _HAILSTONE_TASK},
        )

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["session_id"].startswith("sess_")
        assert body["task"]["instruction"] == _HAILSTONE_TASK
        assert isinstance(body["task"]["id_"], str)
        assert body["task"]["id_"]
        assert body["tools"] == []  # TODO(#8): real tools
        assert body["skills"] == []
        assert body["need"] == "next"

    def test_blank_task_returns_422(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """An empty ``task`` string fails Pydantic's ``min_length``."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post("/api/sessions", json={"task": ""})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_missing_task_returns_422(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A request body without ``task`` is rejected."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post("/api/sessions", json={})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_wrong_type_returns_422(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A wrongly-typed ``task`` field is rejected."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post("/api/sessions", json={"task": 12345})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_now_removed_m1_fields_are_ignored_not_errors(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """Extra/legacy fields (model, think, ...) no longer 422 -- they're
        just ignored, since they're not part of ``CreateSessionRequest``
        anymore (superseded by the discovered builder per ADR-002).
        """
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post(
            "/api/sessions",
            json={
                "task": "do a thing",
                "model": "qwen3:14b",
                "think": False,
                "function_tools": [{"name": "next_number"}],
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_no_configured_builder_returns_500(self) -> None:
        """No builder wired up on this process -> 500, not a client error."""
        client = _client(SessionService())

        response = client.post("/api/sessions", json={"task": "do a thing"})

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_builder_build_failure_returns_502(self) -> None:
        """A failure building the agent from the configured builder -> 502."""
        broken_builder = AsyncMock(spec=LLMAgentBuilder)
        broken_builder.build.side_effect = RuntimeError("mcp unreachable")
        client = _client(SessionService(agent_builder=broken_builder))

        response = client.post("/api/sessions", json={"task": "do a thing"})

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
