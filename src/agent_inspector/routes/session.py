"""Session lifecycle routes (see #3-#6, #11).

Routes are intentionally thin: parse the request, call the relevant
service via its injected dependency, and return. No business logic
lives here -- see ``services/session.py``.

Every domain exception ``services/session.py`` raises (a
``SessionServiceError`` subclass) is deliberately left to propagate
out of these routes uncaught: ``routes/error_handlers.py`` registers a
single shared handler on the ``FastAPI`` app (see #26) that maps every
subclass to its documented status code consistently, so no route needs
its own ``try/except``-to-``HTTPException`` boilerplate.
"""

from typing import Any

from fastapi import APIRouter, status

from agent_inspector.deps import SessionServiceDep
from agent_inspector.schemas import (
    AbortSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    EditResultRequest,
    EditResultResponse,
    EditStepRequest,
    EditStepResponse,
    RejectedTaskResultOut,
    RejectRequest,
    RejectResponse,
    RolloutResponse,
    RunStepResponse,
    SessionConfigOut,
    SessionStateResponse,
    SkillOut,
    TaskOut,
    TaskResultOut,
    TaskStepResultOut,
    TemplatesOut,
    ToolCallTraceOut,
)
from agent_inspector.services.session import (
    NextStepDecisionOutcome,
    get_templates,
)

router = APIRouter()


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    request: CreateSessionRequest,
    session_service: SessionServiceDep,
) -> CreateSessionResponse:
    """Create a new supervised-run session (TRD §6.1).

    Calls ``.build()`` on the ``LLMAgentBuilder`` discovered from the
    user's own script at CLI launch time (see ADR-002 /
    ``discovery.py``) to obtain a fresh ``LLMAgent``, starts a
    ``run_supervised()`` handler for it, then registers the session.

    Args:
        request (CreateSessionRequest): The session config to create.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        CreateSessionResponse: The new session's id, task, the
            discovered agent's real tools/skills (#8/#9), and initial
            ``need`` (always ``"next"``).

    Raises:
        SessionConfigError: Mapped to ``422`` if the request config is
            invalid.
        AgentBuilderNotConfiguredError: Mapped to ``500`` if no
            builder was discovered/configured for this process.
        AgentBuildError: Mapped to ``502`` if the configured builder
            fails to build an agent.
    """
    explicit_only_skills = request.explicit_only_skills
    session = await session_service.create_session_from_config(
        task=request.task,
        skills_scopes=request.skills_scopes,
        explicit_only_skills=explicit_only_skills,
    )

    task = session.handler.task
    # Best-effort, same as `SessionConfig.model`'s docstring: `BaseLLM`
    # has no generic `model` attribute, only concrete implementations
    # (e.g. `OllamaLLM`) do.
    model = getattr(session.agent.llm, "model", None)
    return CreateSessionResponse(
        session_id=session.id,
        task=TaskOut(id_=task.id_, instruction=task.instruction),
        tools=list(session.agent.tools_registry.keys()),
        model=model if isinstance(model, str) else None,
        skills=[
            SkillOut(
                name=name,
                description=skill.frontmatter.description,
                scope=skill.scope,
                explicit_only=name in (explicit_only_skills or set()),
            )
            for name, skill in session.handler.skills.items()
        ],
        need=session.need,
    )


@router.get("/sessions/{session_id}")
async def get_session_state(
    session_id: str,
    session_service: SessionServiceDep,
) -> SessionStateResponse:
    """Return a session's full state for a UI reload (TRD §6.7, see #15).

    Read-only: doesn't touch ``lock_session()`` since nothing here
    mutates the session.

    Args:
        session_id (str): The session identifier.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        SessionStateResponse: ``need``, ``step_counter``, ``rollout``,
            the accumulated tool-call trace, read-only config, and the
            task's final result (``None`` if none exists yet).

    Raises:
        SessionNotFoundError: Mapped to ``404`` if ``session_id`` is
            unknown.
    """
    session = session_service.get_session(session_id)

    state = session_service.get_session_state(session)
    return SessionStateResponse(
        session_id=state.session_id,
        need=state.need,
        step_counter=state.step_counter,
        rollout=state.rollout,
        tool_call_history=[
            ToolCallTraceOut(
                tool_name=trace.tool_name,
                args=trace.args,
                content=trace.content,
                error=trace.error,
            )
            for trace in state.tool_call_history
        ],
        config=SessionConfigOut(
            tools=state.config.tools,
            skills=state.config.skills,
            model=state.config.model,
        ),
        final_result=(
            TaskResultOut(
                task_id=state.final_result.task_id,
                content=state.final_result.content,
            )
            if state.final_result is not None
            else None
        ),
    )


@router.get("/sessions/{session_id}/rollout")
async def get_session_rollout(
    session_id: str,
    session_service: SessionServiceDep,
) -> RolloutResponse:
    """Return a session's rollout text (TRD §6.8, see #15).

    Read-only: doesn't touch ``lock_session()`` since nothing here
    mutates the session.

    Args:
        session_id (str): The session identifier.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        RolloutResponse: ``handler.rollout`` verbatim.

    Raises:
        SessionNotFoundError: Mapped to ``404`` if ``session_id`` is
            unknown.
    """
    session = session_service.get_session(session_id)

    return RolloutResponse(rollout=session_service.get_rollout(session))


@router.get("/templates")
async def get_default_templates() -> TemplatesOut:
    """Return the framework's default prompt templates (TRD §6.9, #15).

    Not session-scoped -- every session's ``LLMAgent`` defaults to the
    same module-level ``default_templates`` instance (see
    ``services.session.get_templates``'s docstring), so this endpoint
    takes no ``session_id`` and needs no ``SessionServiceDep``.

    Returns:
        TemplatesOut: All 11 keys of the framework's
            ``LLMAgentTemplates``.
    """
    return TemplatesOut(**get_templates())


@router.post("/sessions/{session_id}/next-step")
async def post_next_step(
    session_id: str,
    session_service: SessionServiceDep,
) -> dict[str, Any]:
    """Advance a session to its next step or final result (TRD §6.2).

    No request body: the server tracks the previous step result
    internally on the session rather than the client supplying it
    (see ``services.session.Session.last_step_result``).

    Args:
        session_id (str): The session identifier.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        dict[str, Any]: ``{"kind": "next_step", "decision": {...},
            "step": {...}, "need": "run"}`` when the handler produced
            another step, or ``{"kind": "final_result", "result":
            {...}, "need": "approve"}`` when it produced the task's
            final result.

    Raises:
        SessionNotFoundError: Mapped to 404 if ``session_id`` is
            unknown.
        WrongNeedError: Mapped to 409 if the session isn't currently
            waiting on ``next``.
        SessionBusyError: Mapped to 409 if the session already has
            another mutating call in flight.
    """
    outcome = await session_service.get_next_step(session_id)

    if isinstance(outcome, NextStepDecisionOutcome):
        return {
            "kind": outcome.kind,
            "decision": outcome.decision.model_dump(),
            "step": outcome.step.model_dump(),
            "need": outcome.need,
        }

    return {
        "kind": outcome.kind,
        "result": outcome.result.model_dump(),
        "need": outcome.need,
    }


@router.post("/sessions/{session_id}/run-step")
async def post_run_step(
    session_id: str,
    session_service: SessionServiceDep,
) -> RunStepResponse:
    """Execute the session's pending ``TaskStep`` (TRD §6.3, see #5).

    No request body: executes whatever ``TaskStep`` is currently
    pending on the session (recorded by the next-step endpoint, #4).
    Requires ``need == "run"``.

    Args:
        session_id (str): The session identifier.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        RunStepResponse: The step result, tool-call trace, updated
            step counter, and resulting ``need`` (``"next"`` on
            success).

    Raises:
        SessionNotFoundError: Mapped to ``404`` if the session doesn't
            exist.
        SessionBusyError: Mapped to ``409`` if the session is busy.
        WrongNeedError: Mapped to ``409`` if the session isn't waiting
            on ``need == "run"``.
        ToolExecutionError: Mapped to ``502`` if a tool call itself
            raises while executing (e.g. an ``MCPTool`` transport
            failure, or a plain function tool raising) -- distinct
            from ``StepExecutionError`` below.
        StepExecutionError: Mapped to ``502`` if the framework raises
            while executing the step for any other reason
            (LLM/framework-level failure).
        NoPendingStepError: Mapped to ``500`` on a server invariant
            violation (``need == "run"`` with no pending step
            recorded).
    """
    with session_service.lock_session(session_id) as session:
        outcome = await session_service.run_step(session)

    return RunStepResponse(
        result=TaskStepResultOut(
            task_step_id=outcome.result.task_step_id,
            content=outcome.result.content,
        ),
        tool_calls=[
            ToolCallTraceOut(
                tool_name=trace.tool_name,
                args=trace.args,
                content=trace.content,
                error=trace.error,
            )
            for trace in outcome.tool_calls
        ],
        step_counter=outcome.step_counter,
        need=outcome.need,
    )


@router.patch("/sessions/{session_id}/step")
async def patch_step(
    session_id: str,
    request: EditStepRequest,
    session_service: SessionServiceDep,
) -> EditStepResponse:
    """Edit the session's pending ``TaskStep`` (TRD §6.10, see #13).

    Mutates the pending step's instruction in place without consuming
    it or advancing ``need``. Requires ``need == "run"`` -- i.e. must
    be called strictly before ``run-step`` (#5) consumes the step, so
    the edit is guaranteed to be what ``run-step`` actually executes.

    Args:
        session_id (str): The session identifier.
        request (EditStepRequest): The new instruction text.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        EditStepResponse: The mutated step, ``edited: true``, and the
            (unchanged) ``need`` (``"run"``).

    Raises:
        SessionNotFoundError: Mapped to ``404`` if the session doesn't
            exist.
        SessionBusyError: Mapped to ``409`` if the session is busy.
        WrongNeedError: Mapped to ``409`` if the session isn't waiting
            on ``need == "run"``.
        NoPendingStepError: Mapped to ``500`` on a server invariant
            violation (``need == "run"`` with no pending step
            recorded).
    """
    with session_service.lock_session(session_id) as session:
        step = session_service.edit_step(session, request.instruction)
        need = session.need

    return EditStepResponse(step=step, edited=True, need=need)


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: str,
    session_service: SessionServiceDep,
) -> dict[str, Any]:
    """Approve the session's pending ``TaskResult`` (TRD §6.4, see #6).

    No request body is needed: the server already holds the pending
    ``TaskResult`` produced by the ``next-step`` call that put the
    session into ``need="approve"``.

    Args:
        session_id (str): The session identifier.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        dict[str, Any]: ``{"status": "resolved", "result": {"task_id":
            ..., "content": ...}, "need": "done"}``.

    Raises:
        SessionNotFoundError: Mapped to ``404`` if the session doesn't
            exist.
        SessionBusyError: Mapped to ``409`` if the session already has
            a call in flight.
        WrongNeedError: Mapped to ``409`` if the session isn't at
            ``need="approve"``.
        MissingPendingResultError: Mapped to ``500`` if the session
            reached ``need="approve"`` without a pending result stored
            (a server-side bug elsewhere in the ``need``
            orchestration).
    """
    with session_service.lock_session(session_id) as session:
        result = await session_service.complete(session)
        need = session.need

    return {
        "status": "resolved",
        "result": {"task_id": result.task_id, "content": result.content},
        "need": need,
    }


@router.patch("/sessions/{session_id}/result")
async def patch_result(
    session_id: str,
    request: EditResultRequest,
    session_service: SessionServiceDep,
) -> EditResultResponse:
    """Edit the last ``TaskStepResult``'s content (TRD §6.11, see #14).

    Rewrites ``session.last_step_result.content`` and the
    corresponding span of ``session.handler.rollout`` that ``run-step``
    (#5) recorded for it, so the two stay consistent. Requires
    ``need == "next"``.

    Args:
        session_id (str): The session identifier.
        request (EditResultRequest): The edited content.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        EditResultResponse: The edited result, ``edited: true``, and
            the session's (unchanged) ``need`` (``"next"``).

    Raises:
        SessionNotFoundError: Mapped to ``404`` if the session doesn't
            exist.
        SessionBusyError: Mapped to ``409`` if the session is busy.
        WrongNeedError: Mapped to ``409`` if the session isn't waiting
            on ``need == "next"``.
        NoEditableResultError: Mapped to ``409`` if the session has no
            editable ``TaskStepResult`` right now (a fresh session, or
            one that just came out of a rejection).
        MissingRolloutSpanError: Mapped to ``500`` on a server
            invariant violation (an editable result with no recorded
            rollout span).
    """
    with session_service.lock_session(session_id) as session:
        result = session_service.edit_result(session, request.content)
        need = session.need

    return EditResultResponse(
        result=TaskStepResultOut(
            task_step_id=result.task_step_id,
            content=result.content,
        ),
        need=need,
    )


@router.post("/sessions/{session_id}/abort")
async def abort_session(
    session_id: str,
    session_service: SessionServiceDep,
) -> AbortSessionResponse:
    """Abort a session's supervised run (TRD §6.6, see #12).

    No request body: aborts whatever is currently in flight for the
    session, regardless of whether it's waiting on ``next``, ``run``,
    or ``approve``. Discards any pending step/result and resolves the
    framework handler's underlying future with an exception rather
    than a result.

    Args:
        session_id (str): The session identifier.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        AbortSessionResponse: ``{"status": "aborted", "need": "done"}``.

    Raises:
        SessionNotFoundError: Mapped to ``404`` if the session doesn't
            exist.
        SessionBusyError: Mapped to ``409`` if the session already has
            a call in flight.
        WrongNeedError: Mapped to ``409`` if the session is already at
            ``need="done"``.
    """
    with session_service.lock_session(session_id) as session:
        await session_service.abort(session)
        need = session.need

    return AbortSessionResponse(status="aborted", need=need)


@router.post("/sessions/{session_id}/reject")
async def reject_session(
    session_id: str,
    request: RejectRequest,
    session_service: SessionServiceDep,
) -> RejectResponse:
    """Reject the session's pending ``TaskResult`` (TRD §6.5, see #11).

    The server already holds the pending ``TaskResult`` produced by the
    ``next-step`` call that put the session into ``need="approve"``;
    the request only supplies the operator's ``feedback``.

    Args:
        session_id (str): The session identifier.
        request (RejectRequest): The operator's rejection feedback.
        session_service (SessionServiceDep): Injected session service.

    Returns:
        RejectResponse: The rejection (``failed_result_content`` and
            ``feedback``) and the resulting ``need`` (``"next"`` on
            success).

    Raises:
        SessionNotFoundError: Mapped to ``404`` if the session doesn't
            exist.
        SessionBusyError: Mapped to ``409`` if the session already has
            a call in flight.
        WrongNeedError: Mapped to ``409`` if the session isn't at
            ``need="approve"``.
        MissingPendingResultError: Mapped to ``500`` if the session
            reached ``need="approve"`` without a pending result stored
            (a server-side bug elsewhere in the ``need``
            orchestration).
    """
    with session_service.lock_session(session_id) as session:
        rejected = session_service.reject(session, request.feedback)
        need = session.need

    return RejectResponse(
        rejected=RejectedTaskResultOut(
            failed_result_content=rejected.failed_result_content,
            feedback=rejected.feedback,
        ),
        need=need,
    )
