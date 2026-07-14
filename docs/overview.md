# Architecture overview

Agent Inspector is a FastAPI backend + React frontend for manually driving
`llm-agents-from-scratch`'s `LLMAgent.SupervisedTaskHandler` one call at a
time. This doc covers the backend's layering and the session state machine
that the whole API is built around — the thing to read before touching
`services/session.py` or `routes/session.py`.

## Backend layering

```
routes/    -- thin FastAPI routes: parse request, call a service,
              map domain exceptions to HTTPException, return.
services/  -- all business logic. No FastAPI/Starlette imports.
              Raises plain exceptions (errors.py), never HTTPException.
errors.py  -- domain exceptions shared across services/, deliberately
              with no dependency on services/ (see its module docstring).
deps.py    -- FastAPI DI wiring: Annotated[..., Depends(...)] aliases,
              and the process-wide service singletons.
```

One module per domain concern in both `services/` and `routes/` (e.g.
`services/session.py` pairs with `routes/session.py`). Neither package
re-exports from its `__init__.py` — always import from the specific
submodule, so it's unambiguous where something lives.

## Session lifecycle

A `Session` (`services/session.py`) is the in-memory record of one
supervised run: the live `LLMAgent` and `SupervisedTaskHandler`, plus
whatever state the run needs to pause between HTTP calls. `SessionService`
owns every live session in a single in-memory `dict[str, Session]` — see
[ADR-001](../.claude/docs/adr/ADR-001-in-memory-single-process-session-store.md)
for why, and the resulting single-worker-process constraint.

Because the framework's `SupervisedTaskHandler` is caller-driven (you call
`get_next_step()`, then `run_step()`, then `get_next_step()` again, ...) and
doesn't retain anything between those calls itself, `Session` has to carry
the in-flight state across HTTP requests:

| Field               | Set by                    | Consumed by       | Meaning                                                    |
|---------------------|----------------------------|--------------------|--------------------------------------------------------------|
| `pending_step`      | `get_next_step` (next-step) | `run_step` (run-step) | The `TaskStep` waiting to be executed.                     |
| `pending_result`    | `get_next_step` (next-step) | `complete`/`reject`   | The proposed `TaskResult` awaiting operator approval.       |
| `last_step_result`  | `run_step`/`reject`          | `get_next_step`        | What to pass as `previous_step_result` on the next call.    |

Every session also has a non-blocking busy flag (`_busy`, guarded by
`SessionService._registry_lock`): a mutating call acquired via
`lock_session()` raises `SessionBusyError` immediately if another mutating
call on the *same* session is already in flight, rather than queuing.
Different sessions never block each other.

## The `Need` state machine

`Session.need` is the server-authoritative state a session is waiting in —
it's what tells a client (and the UI) which endpoint to call next. It's a
`Literal["next", "run", "approve", "done"]`, not a full `Enum`, so it
serializes straight to JSON with no extra mapping step.

```
                 create session
                       |
                       v
        +--------- "next" <---------+
        |             |             |
 (final result)   (another step) (reject,     "run" -> executing the
        |             |         not yet impl.) pending TaskStep via
        v             v             |          run-step
   "approve"        "run" ---------+
        |             |
  (complete)      (run-step
        |          finishes)
        v             |
     "done" <---------+
        ^
        |
  (abort, from "next" or "run" -- not yet implemented)
```

| Endpoint                                    | Requires `need` | Leaves `need`         |
|----------------------------------------------|-----------------|------------------------|
| `POST /api/sessions`                          | (creates)       | `"next"`               |
| `POST /api/sessions/{id}/next-step`           | `"next"`        | `"run"` or `"approve"` |
| `POST /api/sessions/{id}/run-step`            | `"run"`         | `"next"`               |
| `POST /api/sessions/{id}/complete`            | `"approve"`     | `"done"`               |

Two `SessionService` methods are what actually enforce this (documenting it
in a diagram doesn't, on its own):

- `require_need(session, expected)` — raises `WrongNeedError` if a route is
  called out of turn. Every mutating route calls this first.
- `transition_need(session, target)` — raises `InvalidNeedTransitionError`
  if `target` isn't reachable from the session's current `need` per
  `_NEED_TRANSITIONS`. Every mutating route calls this after successfully
  driving the handler forward.

`reject` and `abort` (the two remaining edges above) aren't implemented yet
— issues #11-#14.

## Known placeholder: the hardcoded tool

`create_session_from_config` (#3) always registers exactly one real tool,
`next_number` (a Hailstone-sequence step function), regardless of what a
client's `function_tools` request field names — arbitrary tool
registration is out of scope for now. The broader direction is to replace
config-driven session creation with something closer to how `gradio`
discovers a user's app: a user writes their own `main.py` that constructs
a real `LLMAgent`, and Agent Inspector discovers and drives that instance
instead of building one from an HTTP request payload. Don't invest further
in generalizing the config-driven path (`function_tools`/`skills_scopes`/
`mcp_servers`) ahead of that change.
