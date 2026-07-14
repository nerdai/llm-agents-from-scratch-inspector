# ADR-001: In-memory, single-process session store

## Status

Accepted

Date: 2026-07-13

## Context

`SessionService` (`src/agent_inspector/services/session.py`) owns every live
session: a `Session` holds a constructed `LLMAgent` plus its
`SupervisedTaskHandler`, keyed by an opaque `session_id` in a plain
`dict[str, Session]` on the `SessionService` instance. A single
`SessionService` instance is created once per process and shared for its
lifetime via `deps.get_session_service`.

`LLMAgent` and `SupervisedTaskHandler` are live Python objects — they hold
open resources (in-flight tool calls, conversation state mid-run) and are not
serializable in any meaningful way. There is no database or external store
anywhere in this project; session state only ever exists as objects on the
Python heap of whichever process created them.

Agent Inspector is a local developer tool: one person runs it against one
agent process on their own machine to step through a `SupervisedTaskHandler`
run. It is not a multi-user or multi-tenant service.

## Decision

We will keep session state entirely in-process, in memory, for the lifetime
of a single worker process. `SessionService` will not be backed by a
database, cache, or any other external store, and the application is only
supported running as a single worker (e.g. `uvicorn ... --workers 1`, the
default).

## Alternatives considered

- **Shared external store (e.g. Redis) keyed by session_id** — would allow
  multiple workers/processes to see the same session registry, but the
  `Session` payload (a live `LLMAgent` + `SupervisedTaskHandler`) isn't
  serializable, so only metadata could live there while the actual agent
  objects would still be pinned to one process. This adds real complexity
  (a new runtime dependency, serialization boundaries) for a single-user
  local tool that doesn't need it.
- **Sticky routing to a fixed worker per session** — avoids the
  serialization problem but requires a load balancer / proxy layer in front
  of the app to pin a session to its worker. Out of scope for a tool meant
  to be run directly with `uvicorn`/the packaged CLI on a developer's
  machine.
- **Persist sessions to disk (e.g. pickle to a file per session)** — doesn't
  solve the underlying problem (a running `LLMAgent`/handler can't be
  meaningfully paused and resumed across a process boundary this way) and
  adds failure modes without a real requirement driving it.

## Consequences

- Simpler implementation: `SessionService` is a plain dict guarded by one
  lock (see the `_registry_lock` fixes from PR #36's review), no
  serialization, no external dependency, no migrations.
- Sessions do not survive a process restart — restarting the server drops
  all live sessions. Acceptable for a local dev tool; would not be
  acceptable if this ever needed to run unattended for long periods.
- **The app must run as a single worker.** Running with
  `--workers N > 1` (or any multi-process deployment: multiple pods, a
  process manager that forks workers) silently breaks session continuity:
  a session created via one worker is invisible to requests routed to
  another worker and will 404 with `SessionNotFoundError`. There is
  currently no guard that prevents starting with `N > 1`; this is
  documented here rather than enforced in code.
- If a future requirement needs multiple concurrent users or horizontal
  scaling, this decision must be revisited — likely superseded by an ADR
  that introduces sticky routing or restructures session state to separate
  serializable metadata from the live agent/handler objects.

## References

- PR #36 (issue #2, `SessionStore`/services split) —
  `src/agent_inspector/services/session.py`
