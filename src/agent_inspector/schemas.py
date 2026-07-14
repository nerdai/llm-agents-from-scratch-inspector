"""Pydantic request/response models for the API (see ``routes/``).

Kept separate from ``routes/`` so route modules stay focused on
dispatch (parse, call a service, map exceptions, return) rather than
wire-format definitions. Framework-agnostic aside from ``pydantic``
itself -- no FastAPI imports here.
"""

from typing import Any

from pydantic import BaseModel, Field

from agent_inspector.services.session import Need


class FunctionToolSpec(BaseModel):
    """A client-supplied function-tool description.

    M1 (issue #3) accepts these but only ever registers the hardcoded
    ``next_number`` tool -- see ``agent_inspector.services.session``.
    Genuine arbitrary function-tool registration is issue #8 (M2).
    """

    name: str
    signature: str | None = None
    source: str | None = None


class CreateSessionRequest(BaseModel):
    """Request body for ``POST /api/sessions`` (TRD §6.1).

    M1 only acts on ``task``, ``model``, and ``think``.
    ``skills_scopes``/``explicit_only_skills``/``mcp_servers`` are
    M2/M3 scope: accepted here so well-formed clients don't get a
    spurious ``422``, but not wired up to anything yet.
    """

    task: str = Field(min_length=1)
    model: str | None = None
    think: bool | None = None
    function_tools: list[FunctionToolSpec] | None = None
    skills_scopes: list[str] | None = None
    explicit_only_skills: list[str] | None = None
    mcp_servers: list[dict[str, Any]] | None = None


class TaskOut(BaseModel):
    """The ``task`` portion of a ``CreateSessionResponse``."""

    id_: str
    instruction: str


class CreateSessionResponse(BaseModel):
    """Response body for ``POST /api/sessions`` (TRD §6.1)."""

    session_id: str
    task: TaskOut
    tools: list[str]
    skills: list[Any] = Field(default_factory=list)
    need: str


class TaskStepResultOut(BaseModel):
    """Wire representation of the framework's ``TaskStepResult``."""

    task_step_id: str
    content: str


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
