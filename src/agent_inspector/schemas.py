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
from pydantic import BaseModel, Field

from agent_inspector.services.session import Need


class CreateSessionRequest(BaseModel):
    """Request body for ``POST /api/sessions`` (TRD §6.1).

    Per ADR-002 (#47): model/tools/skills/memories are no longer sent
    over HTTP -- they're fixed by the ``LLMAgentBuilder`` that
    ``agent-inspector launch <script>`` discovers from the user's own
    script (see ``discovery.py``). ``task`` is the only thing that
    still varies per session.
    """

    task: str = Field(min_length=1)


TaskOut: TypeAlias = Task
"""The ``task`` portion of a ``CreateSessionResponse``.

A companion dev tool for ``llm-agents-from-scratch`` is expected to
couple directly to its data structures rather than shadow them --
``Task`` already has exactly this shape (``id_``, ``instruction``), so
this is a plain alias, not a copy that could drift from the real type.
"""


class CreateSessionResponse(BaseModel):
    """Response body for ``POST /api/sessions`` (TRD §6.1).

    ``tools``/``skills`` are always empty for now -- surfacing the
    discovered builder's real tools/skills is issue #8/#9's job, out
    of scope for #47 (entrypoint discovery itself).
    """

    session_id: str
    task: TaskOut
    tools: list[str] = Field(default_factory=list)  # TODO(#8): real tools
    skills: list[Any] = Field(default_factory=list)  # TODO(#9): real skills
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
    """

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
