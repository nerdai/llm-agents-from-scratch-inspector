"""Tests for ``agent_inspector.services.SessionService``.

Covers the in-memory ``SessionStore`` lifecycle, the per-session busy
lock (issue #2 acceptance criteria: two overlapping mutating calls on
one session -> the second raises ``SessionBusyError``, which the route
layer maps to ``409``), and the ``need`` state machine from TRD §7.
"""

from __future__ import annotations

import asyncio
from typing import cast

import pytest
from llm_agents_from_scratch import LLMAgent

from agent_inspector.services import (
    InvalidNeedTransitionError,
    Session,
    SessionBusyError,
    SessionNotFoundError,
    SessionService,
    WrongNeedError,
)

# SessionService doesn't inspect the agent/handler at runtime (it's
# plain in-memory storage), so a cheap stand-in is enough here; the
# real LLMAgent + SupervisedTaskHandler wiring is issue #3's job.
_FAKE_AGENT = cast(LLMAgent, object())
_FAKE_HANDLER = object()


def _new_session(service: SessionService) -> Session:
    """Create a session on ``service`` using fake agent/handler stubs.

    Args:
        service (SessionService): The service to create the session on.

    Returns:
        Session: The newly created session.
    """
    return service.create_session(agent=_FAKE_AGENT, handler=_FAKE_HANDLER)


class TestSessionLifecycle:
    """Create/get/drop session lifecycle."""

    def test_create_session_generates_opaque_id(self) -> None:
        """Created sessions get a ``sess_``-prefixed unique id."""
        service = SessionService()
        session = _new_session(service)

        assert session.id.startswith("sess_")
        assert session.agent is _FAKE_AGENT
        assert session.handler is _FAKE_HANDLER

    def test_create_session_ids_are_unique(self) -> None:
        """Two created sessions never collide on id."""
        service = SessionService()
        first = _new_session(service)
        second = _new_session(service)

        assert first.id != second.id

    def test_create_session_starts_at_need_next(self) -> None:
        """A freshly created session starts with need='next'."""
        service = SessionService()
        session = _new_session(service)

        assert session.need == "next"

    def test_get_session_returns_created_session(self) -> None:
        """``get_session`` round-trips a created session by id."""
        service = SessionService()
        created = _new_session(service)

        fetched = service.get_session(created.id)

        assert fetched is created

    def test_get_session_unknown_id_raises_not_found(self) -> None:
        """Looking up a bogus id raises SessionNotFoundError."""
        service = SessionService()

        with pytest.raises(SessionNotFoundError):
            service.get_session("sess_does-not-exist")

    def test_drop_session_removes_it(self) -> None:
        """A dropped session can no longer be fetched."""
        service = SessionService()
        session = _new_session(service)

        service.drop_session(session.id)

        with pytest.raises(SessionNotFoundError):
            service.get_session(session.id)

    def test_drop_session_unknown_id_raises_not_found(self) -> None:
        """Dropping a bogus id raises SessionNotFoundError."""
        service = SessionService()

        with pytest.raises(SessionNotFoundError):
            service.drop_session("sess_does-not-exist")


class TestNeedStateMachine:
    """The TRD §7 ``need`` state machine."""

    def test_require_need_passes_on_match(self) -> None:
        """require_need is a no-op when the need matches."""
        service = SessionService()
        session = _new_session(service)

        service.require_need(session, "next")

    def test_require_need_raises_wrong_need_on_mismatch(self) -> None:
        """require_need raises WrongNeedError when the need differs."""
        service = SessionService()
        session = _new_session(service)

        with pytest.raises(WrongNeedError) as exc_info:
            service.require_need(session, "run")

        assert exc_info.value.expected == "run"
        assert exc_info.value.actual == "next"

    @pytest.mark.parametrize(
        ("start", "target"),
        [
            ("next", "run"),  # next-step returns TaskStep
            ("next", "approve"),  # next-step returns TaskResult
            ("run", "next"),  # run-step returns TaskStepResult
            ("approve", "done"),  # complete()
            ("approve", "next"),  # reject(feedback)
            ("next", "done"),  # abort()
            ("run", "done"),  # abort()
        ],
    )
    def test_valid_transitions_succeed(self, start: str, target: str) -> None:
        """Every edge in the TRD §7 diagram is a legal transition."""
        service = SessionService()
        session = _new_session(service)
        session.need = start  # type: ignore[assignment]

        service.transition_need(session, target)  # type: ignore[arg-type]

        assert session.need == target

    @pytest.mark.parametrize(
        ("start", "target"),
        [
            ("next", "next"),
            ("run", "run"),
            ("run", "approve"),
            ("approve", "run"),
            ("approve", "approve"),
            ("done", "next"),
            ("done", "run"),
            ("done", "approve"),
        ],
    )
    def test_invalid_transitions_raise(self, start: str, target: str) -> None:
        """Edges absent from the TRD §7 diagram are rejected."""
        service = SessionService()
        session = _new_session(service)
        session.need = start  # type: ignore[assignment]

        with pytest.raises(InvalidNeedTransitionError):
            service.transition_need(session, target)  # type: ignore[arg-type]


class TestSessionLock:
    """Per-session busy lock (issue #2 acceptance criteria)."""

    def test_lock_session_unknown_id_raises_not_found(self) -> None:
        """Locking a bogus id raises SessionNotFoundError."""
        service = SessionService()

        with (
            pytest.raises(SessionNotFoundError),
            service.lock_session(
                "sess_does-not-exist",
            ),
        ):
            pass

    def test_lock_session_releases_after_use(self) -> None:
        """The lock is released once the with-block exits normally."""
        service = SessionService()
        session = _new_session(service)

        with service.lock_session(session.id):
            pass

        with service.lock_session(session.id):
            pass

    def test_lock_session_releases_after_exception(self) -> None:
        """The lock is released even if the with-block raises."""
        service = SessionService()
        session = _new_session(service)

        with (
            pytest.raises(ValueError, match="boom"),
            service.lock_session(
                session.id,
            ),
        ):
            raise ValueError("boom")

        with service.lock_session(session.id):
            pass

    def test_overlapping_lock_raises_busy(self) -> None:
        """A second lock attempt while the first is held raises busy."""
        service = SessionService()
        session = _new_session(service)

        with (
            service.lock_session(session.id),
            pytest.raises(
                SessionBusyError,
            ) as exc_info,
            service.lock_session(session.id),
        ):
            pass

        assert exc_info.value.session_id == session.id

    async def test_two_overlapping_run_step_calls_second_is_busy(
        self,
    ) -> None:
        """Acceptance criteria: overlapping run-step calls -> second busy.

        Simulates two concurrent HTTP requests both trying to drive
        ``run-step`` on the same session. The first acquires the lock
        and is still "in flight" (an in-progress await) when the
        second arrives; the second must fail immediately with
        SessionBusyError rather than queueing behind the first, so the
        route layer can return 409.
        """
        service = SessionService()
        session = _new_session(service)
        session.need = "run"
        first_call_started = asyncio.Event()
        release_first_call = asyncio.Event()

        async def slow_run_step() -> str:
            with service.lock_session(session.id):
                first_call_started.set()
                await release_first_call.wait()
                return "step result"

        async def overlapping_run_step() -> None:
            await first_call_started.wait()
            with service.lock_session(session.id):
                pass  # pragma: no cover - must raise before this

        first_task = asyncio.create_task(slow_run_step())
        second_task = asyncio.create_task(overlapping_run_step())

        await first_call_started.wait()
        with pytest.raises(SessionBusyError):
            await second_task

        release_first_call.set()
        result = await first_task
        assert result == "step result"
