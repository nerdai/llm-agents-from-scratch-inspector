"""Tests for ``agent_inspector.services.session_store`` (#27 spike).

``SessionService``'s own test suite (``test_session_service.py`` and
friends) already exercises ``InMemorySessionStore`` extensively but
indirectly, through ``SessionService``'s public API -- this file covers
the store's own surface directly: the abstract ``SessionStore``
contract can't be instantiated, and ``InMemorySessionStore``'s
get/set/delete behave exactly like the plain dict they replace
(including on misses/overwrites), independent of any
``SessionService`` lifecycle logic layered on top.
"""

from typing import cast

import pytest
from llm_agents_from_scratch import LLMAgent

from agent_inspector.services.session import Session
from agent_inspector.services.session_store import (
    InMemorySessionStore,
    SessionStore,
)

_FAKE_AGENT = cast(LLMAgent, object())
_FAKE_HANDLER = object()


def _new_session(session_id: str) -> Session:
    """Build a bare ``Session`` for store-level tests.

    Args:
        session_id (str): The id to construct the session with.

    Returns:
        Session: A session with fake agent/handler stubs -- the store
            never inspects these, only stores/retrieves by id.
    """
    return Session(id=session_id, agent=_FAKE_AGENT, handler=_FAKE_HANDLER)


def test_session_store_is_not_directly_instantiable() -> None:
    """``SessionStore`` is an ABC: it can't be constructed directly."""
    with pytest.raises(TypeError):
        SessionStore()  # type: ignore[abstract]


class TestInMemorySessionStore:
    """``InMemorySessionStore`` get/set/delete behavior."""

    def test_get_missing_id_returns_none(self) -> None:
        """A lookup for an id that was never stored returns ``None``."""
        store = InMemorySessionStore()

        assert store.get("sess_missing") is None

    def test_set_then_get_round_trips(self) -> None:
        """A stored session is returned verbatim by a later ``get``."""
        store = InMemorySessionStore()
        session = _new_session("sess_a")

        store.set("sess_a", session)

        assert store.get("sess_a") is session

    def test_set_overwrites_existing_entry(self) -> None:
        """Setting an id that's already stored replaces the old value."""
        store = InMemorySessionStore()
        first = _new_session("sess_a")
        second = _new_session("sess_a")

        store.set("sess_a", first)
        store.set("sess_a", second)

        assert store.get("sess_a") is second

    def test_delete_removes_entry(self) -> None:
        """Deleting a stored id makes subsequent ``get`` return ``None``."""
        store = InMemorySessionStore()
        store.set("sess_a", _new_session("sess_a"))

        store.delete("sess_a")

        assert store.get("sess_a") is None

    def test_delete_missing_id_raises_key_error(self) -> None:
        """Deleting an id that was never stored raises, like a dict."""
        store = InMemorySessionStore()

        with pytest.raises(KeyError):
            store.delete("sess_missing")

    def test_two_stores_do_not_share_state(self) -> None:
        """Each ``InMemorySessionStore`` instance owns its own state."""
        first_store = InMemorySessionStore()
        second_store = InMemorySessionStore()

        first_store.set("sess_a", _new_session("sess_a"))

        assert second_store.get("sess_a") is None

    def test_values_returns_every_stored_session(self) -> None:
        """``values()`` yields every session currently stored (#25)."""
        store = InMemorySessionStore()
        first = _new_session("sess_a")
        second = _new_session("sess_b")
        store.set("sess_a", first)
        store.set("sess_b", second)

        # `Session` is a plain (unhashable) dataclass -- compare by id
        # instead of set-ing the sessions themselves.
        assert {s.id for s in store.values()} == {"sess_a", "sess_b"}

    def test_values_reflects_deletions(self) -> None:
        """A deleted session no longer appears in ``values()``."""
        store = InMemorySessionStore()
        store.set("sess_a", _new_session("sess_a"))

        store.delete("sess_a")

        assert list(store.values()) == []

    def test_values_on_empty_store_is_empty(self) -> None:
        """A fresh store's ``values()`` yields nothing."""
        store = InMemorySessionStore()

        assert list(store.values()) == []
