"""Tests for idle-session eviction (issue #25).

Covers three layers:
    * ``SessionService.evict_idle_sessions`` -- the core eviction logic:
      idle sessions are removed and have their MCP providers closed
      (deduped by provider identity), fresh and busy sessions are left
      alone.
    * ``SessionService.run_eviction_sweep`` -- the background loop that
      calls ``evict_idle_sessions`` on an interval and exits cleanly on
      cancellation.
    * ``server.create_app`` / ``cli.launch`` -- the sweep task is
      started from the app's lifespan, and the TTL is configurable via
      a CLI option (and the env var it reads from).

Mirrors ``test_session_service.py``'s pattern of standing in for a real
``LLMAgent`` with a cheap fake (this module doesn't need a real
``LLMAgent``, just something with a ``tools_registry`` dict), and
stands in for a real MCP server with a lightweight ``_FakeMCPProvider``
double exposing a tracked, async ``close()`` -- no real MCP server is
needed to exercise the dedup-by-provider-identity/close-is-called
logic.
"""

import asyncio
import time
from typing import Any, cast

import pytest
from llm_agents_from_scratch import LLMAgent
from llm_agents_from_scratch.tools.mcp import MCPTool

from agent_inspector.errors.session import SessionNotFoundError
from agent_inspector.services.session import (
    DEFAULT_SESSION_TTL_SECONDS,
    Session,
    SessionService,
    _default_sweep_interval_seconds,
)

_FAKE_HANDLER = object()


class _FakeMCPProvider:
    """A network-free stand-in for ``MCPToolProvider``.

    Only what eviction actually touches: a ``name`` (used in a log
    message) and an async ``close()`` whose call count tests assert
    on. Real ``MCPToolProvider.close()`` tears down a live MCP
    session -- nothing here needs a live server to verify that
    eviction calls it the right number of times.
    """

    def __init__(self, name: str = "fake-provider") -> None:
        self.name = name
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


def _make_mcp_tool(provider: _FakeMCPProvider, name: str) -> MCPTool:
    """Build a real ``MCPTool`` wired to a fake provider double.

    ``MCPTool.__init__`` doesn't validate its ``provider`` argument's
    type at runtime, and eviction's ``isinstance(tool, MCPTool)`` check
    needs a real ``MCPTool`` (not a duck-typed fake) to match -- so
    this uses the real class with a fake ``.provider``.
    """
    return MCPTool(
        provider=cast(Any, provider),
        name=name,
        desc="A fake MCP tool for eviction tests.",
        params_json_schema={},
    )


class _FakeAgent:
    """A cheap stand-in for ``LLMAgent`` exposing only ``tools_registry``.

    Mirrors ``test_session_service.py``'s ``cast(LLMAgent, object())``
    pattern -- ``SessionService`` doesn't otherwise inspect the agent
    at runtime -- but eviction's MCP-provider cleanup does read
    ``tools_registry``, so this fake carries one.
    """

    def __init__(self, tools_registry: dict[str, Any] | None = None) -> None:
        self.tools_registry = tools_registry or {}


def _new_session(
    service: SessionService,
    tools_registry: dict[str, Any] | None = None,
) -> Session:
    """Create a session on ``service`` with a fake agent/handler.

    Args:
        service (SessionService): The service to create the session on.
        tools_registry (dict[str, Any] | None): Tools to attach to the
            fake agent's ``tools_registry``.

    Returns:
        Session: The newly created session.
    """
    agent = cast(LLMAgent, _FakeAgent(tools_registry=tools_registry))
    return service.create_session(agent=agent, handler=_FAKE_HANDLER)


def _backdate(session: Session, idle_for_seconds: float) -> None:
    """Move ``session.last_activity`` into the past by ``idle_for_seconds``.

    Avoids real sleeps in tests that only need "this session has been
    idle for at least N seconds" to be true.
    """
    session.last_activity = time.monotonic() - idle_for_seconds


class TestEvictIdleSessions:
    """``SessionService.evict_idle_sessions`` (#25)."""

    async def test_removes_session_idle_past_ttl(self) -> None:
        """A session idle longer than the TTL is evicted."""
        service = SessionService()
        session = _new_session(service)
        _backdate(session, idle_for_seconds=100)

        evicted = await service.evict_idle_sessions(ttl_seconds=10)

        assert evicted == [session.id]
        with pytest.raises(SessionNotFoundError):
            service.get_session(session.id)

    async def test_keeps_session_within_ttl(self) -> None:
        """A recently-active session is left alone."""
        service = SessionService()
        session = _new_session(service)

        evicted = await service.evict_idle_sessions(ttl_seconds=3600)

        assert evicted == []
        assert service.get_session(session.id) is session

    async def test_skips_busy_session_even_if_idle(self) -> None:
        """A session with a call in flight is never evicted mid-call."""
        service = SessionService()
        session = _new_session(service)

        with service.lock_session(session.id):
            _backdate(session, idle_for_seconds=100)
            evicted = await service.evict_idle_sessions(ttl_seconds=1)

        assert evicted == []
        assert service.get_session(session.id) is session

    async def test_busy_session_is_evicted_once_no_longer_busy(self) -> None:
        """A session skipped for being busy is picked up on a later sweep."""
        service = SessionService()
        session = _new_session(service)

        with service.lock_session(session.id):
            _backdate(session, idle_for_seconds=100)
            assert await service.evict_idle_sessions(ttl_seconds=1) == []

        # lock_session() bumped last_activity on entry; back-date again
        # now that the lock has been released, standing in for time
        # having passed since the call finished.
        _backdate(session, idle_for_seconds=100)
        evicted = await service.evict_idle_sessions(ttl_seconds=1)

        assert evicted == [session.id]

    async def test_only_expired_sessions_are_removed(self) -> None:
        """A sweep only removes the sessions actually past the TTL."""
        service = SessionService()
        stale = _new_session(service)
        fresh = _new_session(service)
        _backdate(stale, idle_for_seconds=100)

        evicted = await service.evict_idle_sessions(ttl_seconds=10)

        assert evicted == [stale.id]
        assert service.get_session(fresh.id) is fresh
        with pytest.raises(SessionNotFoundError):
            service.get_session(stale.id)

    async def test_closes_mcp_provider_on_eviction(self) -> None:
        """An evicted session's MCP tool has its provider closed."""
        service = SessionService()
        provider = _FakeMCPProvider()
        tool = _make_mcp_tool(provider, "mcp__fake__do_thing")
        session = _new_session(service, tools_registry={tool.name: tool})
        _backdate(session, idle_for_seconds=100)

        await service.evict_idle_sessions(ttl_seconds=10)

        assert provider.close_calls == 1

    async def test_dedupes_provider_close_across_shared_tools(self) -> None:
        """Two tools sharing one provider only close it once."""
        service = SessionService()
        provider = _FakeMCPProvider()
        tool_a = _make_mcp_tool(provider, "mcp__fake__tool_a")
        tool_b = _make_mcp_tool(provider, "mcp__fake__tool_b")
        session = _new_session(
            service,
            tools_registry={tool_a.name: tool_a, tool_b.name: tool_b},
        )
        _backdate(session, idle_for_seconds=100)

        await service.evict_idle_sessions(ttl_seconds=10)

        assert provider.close_calls == 1

    async def test_closes_every_distinct_provider(self) -> None:
        """Multiple distinct MCP providers are each closed once."""
        service = SessionService()
        provider_a = _FakeMCPProvider("a")
        provider_b = _FakeMCPProvider("b")
        tool_a = _make_mcp_tool(provider_a, "mcp__a__tool")
        tool_b = _make_mcp_tool(provider_b, "mcp__b__tool")
        session = _new_session(
            service,
            tools_registry={tool_a.name: tool_a, tool_b.name: tool_b},
        )
        _backdate(session, idle_for_seconds=100)

        await service.evict_idle_sessions(ttl_seconds=10)

        assert provider_a.close_calls == 1
        assert provider_b.close_calls == 1

    async def test_non_mcp_tools_are_ignored(self) -> None:
        """A registered tool that isn't an MCPTool is simply skipped."""
        service = SessionService()
        session = _new_session(
            service,
            tools_registry={"plain_tool": object()},
        )
        _backdate(session, idle_for_seconds=100)

        # No error, and the session is still evicted normally.
        evicted = await service.evict_idle_sessions(ttl_seconds=10)

        assert evicted == [session.id]

    async def test_provider_close_error_does_not_block_eviction(self) -> None:
        """A provider that fails to close doesn't stop the session removal."""

        class _BrokenProvider(_FakeMCPProvider):
            async def close(self) -> None:
                self.close_calls += 1
                raise RuntimeError("boom")

        service = SessionService()
        provider = _BrokenProvider()
        tool = _make_mcp_tool(provider, "mcp__broken__tool")
        session = _new_session(service, tools_registry={tool.name: tool})
        _backdate(session, idle_for_seconds=100)

        evicted = await service.evict_idle_sessions(ttl_seconds=10)

        assert evicted == [session.id]
        assert provider.close_calls == 1
        with pytest.raises(SessionNotFoundError):
            service.get_session(session.id)


class TestSweepIntervalDerivation:
    """``_default_sweep_interval_seconds`` -- picking a sweep cadence."""

    def test_derives_a_fraction_of_the_ttl(self) -> None:
        """Mid-range TTLs get ~10% of the TTL as the interval."""
        assert _default_sweep_interval_seconds(1000) == pytest.approx(100)

    def test_clamps_to_a_floor_for_short_ttls(self) -> None:
        """A very short TTL doesn't produce a sub-30s busy-loop interval."""
        assert _default_sweep_interval_seconds(1) == pytest.approx(30)

    def test_clamps_to_a_ceiling_for_long_ttls(self) -> None:
        """A very long TTL doesn't wait more than 300s between sweeps."""
        assert _default_sweep_interval_seconds(100_000) == pytest.approx(300)


class TestRunEvictionSweep:
    """``SessionService.run_eviction_sweep`` -- the background loop."""

    async def test_periodically_evicts_idle_sessions(self) -> None:
        """The loop actually calls evict_idle_sessions on its interval."""
        service = SessionService()
        session = _new_session(service)
        _backdate(session, idle_for_seconds=100)

        task = asyncio.create_task(
            service.run_eviction_sweep(ttl_seconds=1, interval_seconds=0.01),
        )
        try:
            for _ in range(200):
                if session.id not in service._sessions:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Session was not evicted by the sweep loop.")
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    async def test_cancellation_stops_the_loop_cleanly(self) -> None:
        """Cancelling the task exits the loop without a stray exception."""
        service = SessionService()

        task = asyncio.create_task(
            service.run_eviction_sweep(ttl_seconds=60, interval_seconds=10),
        )
        await asyncio.sleep(0)  # let the task start and reach the sleep
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_default_interval_is_derived_when_unset(self) -> None:
        """Passing no interval doesn't error -- it derives one from the TTL."""
        service = SessionService()

        task = asyncio.create_task(
            service.run_eviction_sweep(ttl_seconds=DEFAULT_SESSION_TTL_SECONDS),
        )
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_one_bad_sweep_does_not_kill_the_loop(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An exception from one sweep iteration is logged, not fatal."""
        service = SessionService()
        calls = 0
        expected_calls = 2
        real_evict = service.evict_idle_sessions

        async def _flaky_evict(ttl_seconds: float) -> list[str]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("simulated sweep failure")
            return await real_evict(ttl_seconds)

        monkeypatch.setattr(service, "evict_idle_sessions", _flaky_evict)

        task = asyncio.create_task(
            service.run_eviction_sweep(ttl_seconds=60, interval_seconds=0.01),
        )
        try:
            for _ in range(200):
                if calls >= expected_calls:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Sweep loop did not survive past the failing call.")
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
