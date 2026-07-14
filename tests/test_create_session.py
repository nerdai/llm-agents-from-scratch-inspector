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

from pathlib import Path
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
from llm_agents_from_scratch.data_structures.skill import SkillScope
from llm_agents_from_scratch.tools.simple_function import SimpleFunctionTool

from agent_inspector.deps import get_session_service
from agent_inspector.errors.session import (
    AgentBuilderNotConfiguredError,
    AgentBuildError,
    SessionConfigError,
)
from agent_inspector.server import create_app
from agent_inspector.services.session import SessionService

_HAILSTONE_TASK = "Compute the full Hailstone sequence starting from 4."


def _write_skill(
    root: Path,
    name: str,
    description: str = "A test skill for #9's coverage.",
) -> None:
    """Write a minimal, valid on-disk skill under ``root/.agents/skills``.

    ``.agents/skills`` matches the framework's own ``SKILL_SUBDIR``
    (``skills/constants.py``); ``discover_skills`` resolves
    ``SkillScope.PROJECT`` to ``Path.cwd() / SKILL_SUBDIR``, so tests
    pair this with ``monkeypatch.chdir(root)``.

    Args:
        root (Path): Directory to create ``.agents/skills/<name>/`` under
            (typically a ``tmp_path`` fixture).
        name (str): The skill's name (must match the directory name to
            avoid a (non-fatal) name-mismatch warning).
        description (str): The skill's frontmatter description.
    """
    skill_dir = root / ".agents" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        "Skill body content, non-empty as the framework requires.\n",
    )


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
        assert body["tools"] == []  # no tools registered on the builder
        assert body["skills"] == []  # no skills discoverable in this cwd
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


def add_one(x: int) -> int:
    """Add one to x."""
    return x + 1


def double(x: int) -> int:
    """Double x."""
    return x * 2


class TestCreateSessionResponseTools:
    """``CreateSessionResponse.tools`` reflects real registered tools (#8)."""

    def test_reflects_agents_real_registered_tools(self) -> None:
        """Names come from ``agent.tools_registry``, not a hardcoded name."""
        builder = LLMAgentBuilder(llm=_MockBaseLLM()).with_tools(
            [SimpleFunctionTool(add_one), SimpleFunctionTool(double)],
        )
        client = _client(SessionService(agent_builder=builder))

        response = client.post("/api/sessions", json={"task": _HAILSTONE_TASK})

        assert response.status_code == status.HTTP_201_CREATED
        assert set(response.json()["tools"]) == {"add_one", "double"}

    def test_no_tools_registered_returns_empty_list(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A builder with no tools -> ``tools: []``, not a placeholder name."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post("/api/sessions", json={"task": _HAILSTONE_TASK})

        assert response.json()["tools"] == []

    async def test_service_layer_session_agent_has_real_tools_registry(
        self,
    ) -> None:
        """``session.agent.tools_registry`` (service layer) reflects the
        builder's configured tools, independent of response wiring."""
        builder = LLMAgentBuilder(llm=_MockBaseLLM()).with_tool(
            SimpleFunctionTool(add_one),
        )
        service = SessionService(agent_builder=builder)

        session = await service.create_session_from_config(task=_HAILSTONE_TASK)

        assert set(session.agent.tools_registry) == {"add_one"}


class TestCreateSessionFromConfigSkills:
    """``skills_scopes``/``explicit_only_skills`` reach ``run_supervised()``
    (#9), at the ``SessionService`` layer."""

    async def test_skills_scopes_restricts_discovery(
        self,
        agent_builder: LLMAgentBuilder,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Passing ``skills_scopes=[PROJECT]`` reaches ``run_supervised()``:
        the project-scope skill on disk is discovered."""
        _write_skill(tmp_path, "greeter")
        monkeypatch.chdir(tmp_path)
        service = SessionService(agent_builder=agent_builder)

        session = await service.create_session_from_config(
            task=_HAILSTONE_TASK,
            skills_scopes=[SkillScope.PROJECT],
        )

        assert set(session.handler.skills) == {"greeter"}

    async def test_skills_scopes_user_only_excludes_project_skill(
        self,
        agent_builder: LLMAgentBuilder,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Passing ``skills_scopes=[USER]`` (excluding PROJECT) means the
        project-scope skill on disk is *not* discovered -- proving the
        parameter genuinely reaches ``run_supervised()`` and narrows
        discovery, rather than the framework's own ``[USER, PROJECT]``
        default being used regardless of what's passed."""
        _write_skill(tmp_path, "greeter")
        monkeypatch.chdir(tmp_path)
        service = SessionService(agent_builder=agent_builder)

        session = await service.create_session_from_config(
            task=_HAILSTONE_TASK,
            skills_scopes=[SkillScope.USER],
        )

        assert session.handler.skills == {}

    async def test_explicit_only_skills_reaches_run_supervised(
        self,
        agent_builder: LLMAgentBuilder,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``explicit_only_skills`` is forwarded to ``run_supervised()``:
        the skill stays discovered (loadable) rather than being dropped
        from ``handler.skills`` outright. The catalog-visibility effect
        of ``explicit_only_skills`` (the framework's own
        ``UseSkillTool._visible``) is an internal implementation detail,
        so it's covered at the route layer instead, via the observable
        ``explicit_only: true`` tag -- see
        ``TestCreateSessionRouteSkills.
        test_explicit_only_skills_are_tagged_but_still_listed``."""
        _write_skill(tmp_path, "greeter")
        monkeypatch.chdir(tmp_path)
        service = SessionService(agent_builder=agent_builder)

        session = await service.create_session_from_config(
            task=_HAILSTONE_TASK,
            skills_scopes=[SkillScope.PROJECT],
            explicit_only_skills={"greeter"},
        )

        assert "greeter" in session.handler.skills

    async def test_omitting_skills_fields_still_works(
        self,
        agent_builder: LLMAgentBuilder,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Both fields are optional: omitting them still creates a session,
        and the framework's own default (scan USER + PROJECT) applies."""
        _write_skill(tmp_path, "greeter")
        monkeypatch.chdir(tmp_path)
        service = SessionService(agent_builder=agent_builder)

        session = await service.create_session_from_config(task=_HAILSTONE_TASK)

        assert "greeter" in session.handler.skills


class TestCreateSessionRouteSkills:
    """``CreateSessionResponse.skills`` (route layer, #9)."""

    def test_omitting_skills_fields_returns_empty_skills(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """No skills discoverable from the test cwd -> ``skills: []``."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post("/api/sessions", json={"task": _HAILSTONE_TASK})

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["skills"] == []

    def test_discovered_skill_is_surfaced_with_scope_and_not_explicit_only(
        self,
        agent_builder: LLMAgentBuilder,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A regular (non-explicit-only) skill is reflected with its real
        name/description/scope, tagged ``explicit_only: false``."""
        _write_skill(tmp_path, "greeter", description="Greets the user.")
        monkeypatch.chdir(tmp_path)
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post(
            "/api/sessions",
            json={"task": _HAILSTONE_TASK, "skills_scopes": ["project"]},
        )

        assert response.status_code == status.HTTP_201_CREATED
        skills = response.json()["skills"]
        assert len(skills) == 1
        assert skills[0]["name"] == "greeter"
        assert skills[0]["description"] == "Greets the user."
        assert skills[0]["scope"] == "project"
        assert skills[0]["explicit_only"] is False

    def test_explicit_only_skills_are_tagged_but_still_listed(
        self,
        agent_builder: LLMAgentBuilder,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Explicit-only skills stay in the response (still invocable by
        name), but are tagged ``explicit_only: true`` so the UI can
        distinguish them from regular, model-catalog-visible skills."""
        _write_skill(tmp_path, "greeter")
        _write_skill(tmp_path, "farewell")
        monkeypatch.chdir(tmp_path)
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post(
            "/api/sessions",
            json={
                "task": _HAILSTONE_TASK,
                "skills_scopes": ["project"],
                "explicit_only_skills": ["greeter"],
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        by_name = {s["name"]: s for s in response.json()["skills"]}
        assert set(by_name) == {"greeter", "farewell"}
        assert by_name["greeter"]["explicit_only"] is True
        assert by_name["farewell"]["explicit_only"] is False

    def test_invalid_skills_scope_returns_422(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A ``skills_scopes`` value outside ``{"user", "project"}`` 422s
        at the Pydantic layer, before reaching the service."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.post(
            "/api/sessions",
            json={"task": _HAILSTONE_TASK, "skills_scopes": ["nope"]},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
