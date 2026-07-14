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
    TaskStep,
    TaskStepResult,
)
from llm_agents_from_scratch.data_structures.skill import SkillScope
from pydantic import BaseModel, Field

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
    skills_scopes: list[Literal["user", "project"]] | None = None
    explicit_only_skills: list[str] | None = None


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
    each was requested as ``explicit_only_skills``.
    """

    session_id: str
    task: TaskOut
    tools: list[str] = Field(default_factory=list)
    skills: list[SkillOut] = Field(default_factory=list)
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
