"""Pluggable ``Session`` storage backends (spike, see #27).

``SessionService`` (``services/session.py``) owns session *lifecycle*
(the ``need`` state machine, locking, driving the framework handler);
this module owns session *storage* -- the seam between that logic and
wherever ``Session`` objects actually live. ``SessionStore`` is the
abstract interface; ``InMemorySessionStore`` is the only concrete
implementation today, extracted verbatim from what was previously a
plain ``dict[str, Session]`` directly on ``SessionService``.

Deliberately minimal: ``SessionService`` only ever needs to look up a
session by id, store one, remove one, and (as of the TTL-eviction
sweep, #25) iterate every stored session -- see each method's
docstring below for exactly which ``SessionService`` call sites it
replaces.

An ``ABC`` (not ``typing.Protocol``) to match this codebase's existing
style: the framework this project wraps (``llm_agents_from_scratch``)
defines its own extension points as ``ABC``s (e.g. ``BaseTool``,
``AsyncBaseTool`` in ``llm_agents_from_scratch.base.tool``), and
nothing elsewhere in ``agent_inspector`` uses ``Protocol``.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from agent_inspector.services.session import Session


class SessionStore(ABC):
    """Abstract interface for storing/retrieving ``Session`` objects.

    Implementations are not required to be thread-safe on their own --
    ``SessionService`` serializes every access through its own
    ``_registry_lock`` (see ``services/session.py``), so a store only
    needs to correctly perform the operation it's asked for. A future
    backend that talks to an external system (and so needs its own
    connection-level locking/transactions) is free to add that
    internally without changing this contract.

    **Identity contract**: ``get(id)`` must return the exact same
    mutable ``Session`` instance a prior ``set(id, session)`` was
    given -- never a reconstructed copy. ``SessionService`` relies on
    this: ``lock_session`` and ``transition_need`` (see
    ``services/session.py``) mutate a fetched ``Session`` in place
    (``session._busy``, ``session.need``, ...) and never call
    ``set()`` again afterward, so those mutations are only durable if
    ``get()`` keeps handing back a reference to the one object the
    store holds. A backend that serializes ``Session`` on `set()` and
    deserializes a fresh copy on every `get()` would silently break
    the busy-lock and the ``need`` state machine -- see
    ``InMemorySessionStore`` below for the trivial (dict-reference)
    case that already satisfies this, and this module's docstring for
    why ``Session`` isn't meaningfully serializable in the first place
    (a live ``LLMAgent``/``SupervisedTaskHandler``/MCP connections, not
    plain data).
    """

    @abstractmethod
    def get(self, session_id: str) -> "Session | None":
        """Look up a session by id.

        Replaces what was previously ``self._sessions.get(session_id)``
        directly on ``SessionService`` -- used by ``get_session``,
        ``drop_session``, and ``lock_session`` to fetch a session, and
        by ``create_session`` (via ``is not None``) to check a
        candidate id isn't already taken.

        Must return the same mutable instance a prior ``set()`` call
        was given for this id -- see this class's "Identity contract"
        note. Not a copy, not a reconstruction from serialized data.

        Args:
            session_id (str): The session identifier.

        Returns:
            Session | None: The matching session, or ``None`` if no
                session with that id is stored.
        """

    @abstractmethod
    def set(self, session_id: str, session: "Session") -> None:
        """Store a session under an id, overwriting any existing entry.

        Replaces what was previously
        ``self._sessions[session_id] = session`` directly on
        ``SessionService`` -- used by ``create_session`` to register a
        newly constructed session.

        The stored object is exactly what a later ``get()`` for this
        id must return (see this class's "Identity contract" note) --
        implementations must keep a reference to ``session`` itself,
        not a copy.

        Args:
            session_id (str): The session identifier to store under.
            session (Session): The session to store.
        """

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Remove a stored session by id.

        Replaces what was previously ``del self._sessions[session_id]``
        directly on ``SessionService`` -- used by ``drop_session``.
        Callers are responsible for confirming the id exists (e.g. via
        ``get()``) before calling this; per Python's own ``dict``
        semantics that ``InMemorySessionStore`` mirrors, deleting a
        missing id is a bug in the caller, not something this
        interface defines a return value or exception for.

        Args:
            session_id (str): The session identifier to remove.
        """

    @abstractmethod
    def values(self) -> "Iterable[Session]":
        """Iterate every currently stored session, in no particular order.

        Replaces what was previously ``self._sessions.values()``
        directly on ``SessionService`` -- used by
        ``evict_idle_sessions`` (#25) to find idle sessions across the
        whole registry. A backend fronting an external system (e.g. a
        database) should expect this to be called periodically over
        the store's full contents; if that's ever expensive at scale,
        that's a reason to add a more targeted query method later, not
        a reason to skip implementing this one now.

        Returns:
            Iterable[Session]: Every session currently stored. Same
                identity contract as ``get()`` -- these must be the
                live, mutable instances, not copies.
        """


class InMemorySessionStore(SessionStore):
    """The default, process-local ``SessionStore`` (ADR-001).

    A thin wrapper around a plain ``dict[str, Session]`` -- exactly
    the storage ``SessionService`` used inline before this interface
    existed. Per ADR-001, session payloads (a live ``LLMAgent`` +
    ``SupervisedTaskHandler``) aren't meaningfully serializable, so
    this remains the only implementation for now; see this module's
    docstring and the issue #27 PR description for what a persistent
    backend would additionally need to handle.
    """

    def __init__(self) -> None:
        """Initialize an empty store."""
        self._sessions: dict[str, "Session"] = {}

    def get(self, session_id: str) -> "Session | None":
        """See ``SessionStore.get``.

        Trivially satisfies the identity contract: a plain ``dict``
        already stores/returns object references, never copies.
        """
        return self._sessions.get(session_id)

    def set(self, session_id: str, session: "Session") -> None:
        """See ``SessionStore.set``."""
        self._sessions[session_id] = session

    def delete(self, session_id: str) -> None:
        """See ``SessionStore.delete``."""
        del self._sessions[session_id]

    def values(self) -> "Iterable[Session]":
        """See ``SessionStore.values``."""
        return self._sessions.values()
