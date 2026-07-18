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
              Raises plain exceptions (errors/), never HTTPException.
errors/    -- domain exceptions, one module per domain concern,
              deliberately with no dependency on the module they
              serve (see its package docstring).
deps.py    -- FastAPI DI wiring: Annotated[..., Depends(...)] aliases,
              and the process-wide service singletons.
```

One module per domain concern in `services/`, `routes/`, and `errors/`
(e.g. `services/session.py` pairs with `routes/session.py` and
`errors/session.py`). None of these packages re-export from their
`__init__.py` — always import from the specific submodule, so it's
unambiguous where something lives.

## Session lifecycle

A `Session` (`services/session.py`) is the in-memory record of one
supervised run: the live `LLMAgent` and `SupervisedTaskHandler`, plus
whatever state the run needs to pause between HTTP calls. `SessionService`
owns every live session's lifecycle and delegates storage to a pluggable
`SessionStore` (`services/session_store.py`) — `InMemorySessionStore`
(a plain `dict[str, Session]`) by default and today the only
implementation — see
[ADR-001](adr/ADR-001-in-memory-single-process-session-store.md)
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

## Entrypoint discovery (ADR-002)

`POST /api/sessions` no longer builds an `LLMAgent` from HTTP config
(`model`/`think`/`function_tools`/...) — see
[ADR-002](adr/ADR-002-convention-based-entrypoint-discovery.md)
for the full rationale. Instead:

1. The user writes a Python script (e.g. `main.py`) that constructs an
   `LLMAgentBuilder` (`llm_agents_from_scratch.agent.builder`) — real
   tools, skills, memories, and a model, all in code via its fluent
   `with_*` methods — and exposes it at a well-known module-level name:

   ```python
   from llm_agents_from_scratch import LLMAgentBuilder
   from llm_agents_from_scratch.llms import OllamaLLM

   agent_builder = (
       LLMAgentBuilder()
       .with_llm(OllamaLLM(model="qwen3:14b"))
       .with_tool(my_tool)
   )
   ```

2. `agent-inspector launch main.py` imports that script (standard
   `importlib` machinery against the file path, the same mechanism
   Gradio uses to discover a user's `demo` object) and looks up
   `agent_builder` on it. See `discovery.py` for the exact mechanism
   and every failure mode it turns into a clear, actionable error
   (script not found, import failure, missing/wrong-typed
   `agent_builder`, or a builder with no `.with_llm(...)` called) —
   all of which are caught and reported at `launch` time, not lazily
   on the first `POST /sessions`.

3. `SessionService.create_session_from_config` calls
   `agent_builder.build()` once per new session (see `deps.py`'s
   `configure_entrypoint`, which wires the CLI-discovered builder
   into the process-wide `SessionService`). Each call returns an
   independent `LLMAgent` — this matters because `run_step`'s
   tool-call recording temporarily mutates `session.agent
   .tools_registry` in place, and two sessions sharing one `LLMAgent`
   instance would race on that mutation.

`task` (the instruction to run) is the only thing that still comes from
the client at session-creation time — `CreateSessionRequest` is just
`{task: str}`. Surfacing the discovered builder's real tools/skills in
`CreateSessionResponse` is issue #8/#9's job, not #47's.

### Optional `default_task` (#86)

A script can also expose a module-level `default_task` (a `Task`),
pre-filled into the UI's task field at launch time instead of a value
hardcoded in the frontend:

```python
from llm_agents_from_scratch.data_structures import Task

default_task = Task(instruction="Compute next_number starting from 4.")
```

Unlike `agent_builder`, its absence isn't an error — `discover_entrypoint`
just reports `None`, and the field starts blank. `GET /api/agent-info`
surfaces it (alongside `model`/`tools`, both fixed by the discovered
builder and knowable without a session, unlike `skills`) so the config
rail can show it before `POST /sessions` is ever called.
