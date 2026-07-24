"""Pydantic request/response models for the API (see ``routes/``).

Kept separate from ``routes/`` so route modules stay focused on
dispatch (parse, call a service, map exceptions, return) rather than
wire-format definitions. Framework-agnostic aside from ``pydantic``
itself -- no FastAPI imports here.
"""

from typing import Any, Literal, TypeAlias

from llm_agents_from_scratch.data_structures import (
    RejectedTaskResult,
    Task,
    TaskResult,
    TaskStep,
    TaskStepResult,
)
from llm_agents_from_scratch.data_structures.skill import SkillScope
from pydantic import BaseModel, ConfigDict, Field

from agent_inspector.services.session import Need


class CreateSessionRequest(BaseModel):
    """Request body for ``POST /api/sessions`` (TRD §6.1).

    Per ADR-002 (#47): model/tools/skills/memories are no longer sent
    over HTTP -- they're fixed by the ``LLMAgentBuilder`` that
    ``agent-inspector launch <script>`` discovers from the user's own
    script (see ``discovery.py``). ``task`` is the only thing that
    still varies per session that way.

    ``skills_scopes``/``explicit_only_skills`` (#9) are the one
    exception: unlike model/tools/memories, they're call-time
    arguments to the framework's own ``LLMAgent.run_supervised()``,
    not ``LLMAgentBuilder`` construction config -- there's no
    ``builder.with_skills_scopes(...)``-style method for a script to
    fix a default through, so they stay legitimate per-request fields
    here, passed straight through to ``run_supervised()``. Both are
    optional and default to ``None``, which the framework itself
    defaults to "scan both scopes" / "no skills hidden".
    """

    task: str = Field(min_length=1)
    skills_scopes: list[SkillScope] | None = None
    explicit_only_skills: set[str] | None = None


TaskOut: TypeAlias = Task
"""The ``task`` portion of a ``CreateSessionResponse``.

A companion dev tool for ``llm-agents-from-scratch`` is expected to
couple directly to its data structures rather than shadow them --
``Task`` already has exactly this shape (``id_``, ``instruction``), so
this is a plain alias, not a copy that could drift from the real type.
"""


class SkillOut(BaseModel):
    """Wire representation of one of the session's discovered skills (#9).

    Built from the framework's own ``Skill`` (``skills/skill.py``),
    which isn't itself a Pydantic model, so -- unlike ``TaskOut``/
    ``TaskStepOut`` above -- this is a real (if thin) mapping rather
    than a plain ``TypeAlias``. ``scope`` couples directly to the
    framework's own ``SkillScope`` enum per this project's convention
    of preferring explicit coupling to the framework's real types over
    shadowing them.

    Attributes:
        name (str): The skill's name (``Skill.frontmatter.name``, the
            dict key in ``TaskHandler.skills``).
        description (str): The skill's description
            (``Skill.frontmatter.description``).
        scope (SkillScope): Which scope the skill was discovered under
            (``Skill.scope`` -- ``PROJECT`` takes precedence over
            ``USER`` on a name collision).
        explicit_only (bool): Whether this skill was requested as
            ``explicit_only_skills`` for this session. The framework's
            ``UseSkillTool`` hides such skills from the *model's*
            visible tool catalog (its ``_visible`` list) while still
            allowing the model to invoke them directly by name -- so
            ``True`` here means "hidden from the catalog, not
            unavailable."
    """

    name: str
    description: str
    scope: SkillScope
    explicit_only: bool


class CreateSessionResponse(BaseModel):
    """Response body for ``POST /api/sessions`` (TRD §6.1).

    ``tools`` reflects the discovered builder's real, registered tool
    names (``LLMAgent.tools_registry``, see #8). ``skills`` reflects
    the real skills the framework discovered for this session
    (``SupervisedTaskHandler.skills``, see #9), tagged with whether
    each was requested as ``explicit_only_skills``. ``model`` is
    best-effort, same rationale as ``SessionConfigOut.model`` below --
    ``BaseLLM`` has no generic ``model`` attribute, only concrete
    implementations do.
    """

    session_id: str
    task: TaskOut
    tools: list[str] = Field(default_factory=list)
    skills: list[SkillOut] = Field(default_factory=list)
    model: str | None = None
    need: str


TaskStepResultOut: TypeAlias = TaskStepResult
"""Wire representation of the framework's ``TaskStepResult`` -- a plain
alias, same rationale as ``TaskOut`` above."""


class ToolCallTraceOut(BaseModel):
    """Wire representation of one executed tool call."""

    tool_name: str
    args: dict[str, Any]
    content: Any
    error: bool


class RunStepResponse(BaseModel):
    """Response body for ``POST /api/sessions/{id}/run-step`` (see #5)."""

    result: TaskStepResultOut
    tool_calls: list[ToolCallTraceOut]
    step_counter: int
    need: Need


TaskStepOut: TypeAlias = TaskStep
"""Wire representation of the framework's ``TaskStep`` -- a plain alias,
same rationale as ``TaskOut`` above."""


class EditStepRequest(BaseModel):
    """Request body for ``PATCH /api/sessions/{id}/step`` (see #13)."""

    instruction: str = Field(min_length=1)


class EditStepResponse(BaseModel):
    """Response body for ``PATCH /api/sessions/{id}/step`` (see #13)."""

    step: TaskStepOut
    edited: bool = True
    need: Need


class AbortSessionResponse(BaseModel):
    """Response body for ``POST /api/sessions/{id}/abort`` (see #12)."""

    status: Literal["aborted"] = "aborted"
    need: Literal["done"] = "done"


class RejectRequest(BaseModel):
    """Request body for ``POST /api/sessions/{id}/reject`` (see #11)."""

    feedback: str = Field(min_length=1)


RejectedTaskResultOut: TypeAlias = RejectedTaskResult
"""Wire representation of the framework's ``RejectedTaskResult`` -- a
plain alias, same rationale as ``TaskOut``/``TaskStepResultOut`` above:
its fields (``failed_result_content``, ``feedback``) already match the
TRD §6.5 response shape exactly."""


class RejectResponse(BaseModel):
    """Response body for ``POST /api/sessions/{id}/reject`` (see #11)."""

    rejected: RejectedTaskResultOut
    need: Need


class EditResultRequest(BaseModel):
    """Request body for ``PATCH /api/sessions/{id}/result`` (see #14)."""

    content: str


class EditResultResponse(BaseModel):
    """Response body for ``PATCH /api/sessions/{id}/result`` (see #14)."""

    result: TaskStepResultOut
    edited: bool = True
    need: Need


class RolloutResponse(BaseModel):
    """Response body for ``GET /api/sessions/{id}/rollout`` (see #15).

    ``handler.rollout`` is confirmed a plain ``str`` (TRD §6.8) -- this
    wraps it in a minimal, named response shape rather than returning a
    bare string.
    """

    rollout: str


class TemplatesOut(BaseModel):
    """Wire representation of ``GET /api/templates`` (TRD §6.9, see #15).

    Not a ``TypeAlias`` to the framework's own ``LLMAgentTemplates``
    like ``TaskOut``/``TaskStepResultOut`` above, unlike those: it's a
    ``TypedDict`` (not a Pydantic ``BaseModel``), and Pydantic can only
    build a schema for a ``typing.TypedDict`` on Python >= 3.12 --
    this project supports 3.10+, so using it directly as a FastAPI
    response type breaks on 3.10/3.11 (confirmed via CI:
    ``PydanticUserError: Please use typing_extensions.TypedDict``).
    A real ``BaseModel`` with the same 11 fields, populated from
    ``default_templates`` by keyword unpacking, sidesteps that
    entirely while still returning all 11 keys verbatim (per the
    issue's own recommendation -- simplest, most future-proof, no
    curated subset to drift from the framework's own type).

    ``extra="allow"`` so that if the framework ever adds template
    keys, they're preserved in the response rather than silently
    dropped by Pydantic's default extra-field handling.
    """

    model_config = ConfigDict(extra="allow")

    system_message: str
    get_next_step: str
    step_rollout_chat_message: str
    step_rollout_content_instruction: str
    step_rollout_content_tool_call_request: str
    run_step_system_message_without_rollout: str
    run_step_system_message: str
    run_step_user_message: str
    skills_catalog: str
    memories: str
    approval_rejection_feedback: str


class AgentInfoOut(BaseModel):
    """Wire representation of ``GET /api/agent-info`` (see #86, #90).

    The discovered agent's static properties -- knowable from the
    ``LLMAgentBuilder`` itself, without creating a session -- unlike
    ``skills``, which stay session-only since they depend on
    per-session ``skills_scopes``/``explicit_only_skills``. See
    ``services.session.get_agent_info`` for what each field means
    (and ``tools``' MCP-provider caveat) and why ``model`` is
    best-effort.

    ``ollama_host``/``is_local_ollama`` are both ``None`` unless the
    discovered agent's LLM is an ``OllamaLLM`` -- there's no
    local-daemon concept for anything else. When it is one,
    ``is_local_ollama`` distinguishes a local daemon (``GET
    /api/ollama/status``'s reachability check is meaningful) from a
    remote/cloud one, e.g. Ollama Cloud (it isn't -- see
    ``services.session._ollama_host_info``).
    """

    model: str | None = None
    tools: list[str] = Field(default_factory=list)
    default_task: TaskOut | None = None
    ollama_host: str | None = None
    is_local_ollama: bool | None = None


class SessionConfigOut(BaseModel):
    """Wire representation of ``SessionConfig`` (see #15).

    See ``services.session.SessionConfig``'s docstring for what each
    field means and why ``model`` is best-effort.
    """

    tools: list[str]
    skills: list[str]
    model: str | None = None


TaskResultOut: TypeAlias = TaskResult
"""Wire representation of the framework's ``TaskResult`` -- a plain
alias, same rationale as ``TaskOut`` above."""


class SessionStateResponse(BaseModel):
    """Response body for ``GET /api/sessions/{id}`` (TRD §6.7, see #15).

    Full session state for a UI reload. See
    ``services.session.SessionService.get_session_state``'s docstring
    for exactly how ``final_result`` is derived across the ``need``
    lifecycle.
    """

    session_id: str
    need: Need
    step_counter: int
    rollout: str
    tool_call_history: list[ToolCallTraceOut]
    config: SessionConfigOut
    final_result: TaskResultOut | None = None


class OllamaStatusResponse(BaseModel):
    """Response body for ``GET /api/ollama/status`` (TRD §12, see #18).

    Always a ``200`` -- an unreachable daemon is a normal outcome
    (``reachable: False``), not an error surface. The UI's ``ollama
    serve`` hint is driven by that flag, not an HTTP status code.
    """

    reachable: bool
    version: str | None = None
