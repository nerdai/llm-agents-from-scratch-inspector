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
