# ADR-002: Convention-based entrypoint discovery, not config-driven session creation

## Status

Proposed

Date: 2026-07-14

## Context

M1 built session creation as config-driven: `POST /api/sessions` accepts a
`CreateSessionRequest` JSON body (`task`, `model`, `think`,
`function_tools[]`, `skills_scopes`, `explicit_only_skills`,
`mcp_servers`), and `SessionService.create_session_from_config()`
constructs a fresh `LLMAgent` from it server-side. M1 only actually acts on
`task`/`model`/`think`; every session gets exactly one hardcoded tool
(`next_number`) regardless of what `function_tools` names, and the rest of
the config is accepted-but-ignored scaffolding for M2 to wire up.

Scoping M2's function-tool registration issue (#8: accept
`function_tools[]` as `{name, signature, source}` and register them as
real, callable tools) surfaced a hard blocker: `SimpleFunctionTool`/
`AsyncSimpleFunctionTool` require a real Python callable object.
`llm-agents-from-scratch` v0.0.20 has no mechanism anywhere to build a
callable tool from a signature string plus a source-code string — there's
no `exec`/`compile` path in the framework at all (confirmed via full
source search). Building that ourselves would mean writing our own
exec/compile sandbox to turn client-submitted request-body text into
running server-side code — a real arbitrary-code-execution security
surface, for a feature whose only purpose is letting a user re-describe a
tool they could have just... written as a Python function.

That's the actual crux: Agent Inspector is a companion dev tool for
people already writing `llm-agents-from-scratch` code, not an end-user
product fronting a black-box agent. The target user already has a Python
environment and already knows how to write an `LLMAgent`, tools, and
skills in code — asking them to re-serialize all of that into an HTTP JSON
payload just to get a UI is friction with no corresponding benefit, and
it's what's forcing the exec/compile problem in the first place.

Two existing tools were considered for how their "point me at your thing"
model works:

- **MCP Inspector** connects to a target MCP server as a client over a
  wire protocol (stdio/SSE), spawning it as a subprocess and calling the
  protocol's own introspection RPCs (`tools/list`, etc.) to discover its
  capabilities. This doesn't transfer here: MCP is a self-describing
  network protocol between separate processes/languages; we're in the
  same Python process as the user's code, not bridging a protocol
  boundary. There's nothing analogous to a `tools/list` RPC on a bare
  `LLMAgent` object.
- **Gradio** discovers a user's app by importing their script and looking
  for a conventionally-named object (`demo`) at module scope. This maps
  directly: both cases are "import Python code in the same process and
  find a known object," not "speak a protocol to a separate service."

## Decision

We will replace config-driven session creation with convention-based
entrypoint discovery: the user authors a Python script (e.g. `main.py`)
that builds their `LLMAgent` (real tools, skills, memories, model — all in
code) and exposes it via a well-known module-level name. Agent Inspector's
CLI is pointed at that script (`agent-inspector launch main.py`, exact
flag TBD), imports it, and discovers the agent by that convention.

The discovered object must be a **zero-argument factory callable that
returns a fresh `LLMAgent`**, not a bare `LLMAgent` instance. This isn't
just a style preference: `SessionService` already constructs a new
`LLMAgent` per session (`create_session_from_config`), and there's a real
correctness reason to keep doing that. `run_step()`'s tool-call recording
(`_wrap_tool_for_recording` in `services/session.py`) temporarily mutates
`session.agent.tools_registry` in place for the duration of the call, then
restores it. If multiple sessions shared one `LLMAgent` instance, two
sessions running steps concurrently would race on that same registry
mutation. A factory convention (e.g. a module-level `def create_agent() ->
LLMAgent:`) keeps "one real `LLMAgent` instance per session" exactly as it
is today — only the source of the agent's configuration moves from an HTTP
request body to the user's own script.

`task` (the actual instruction to run) still comes from the UI at session
creation time — that's inherent to "drive one task at a time," not
agent configuration. So `CreateSessionRequest` shrinks to essentially just
`{task: str}` once model/tools/skills/memories are fixed by the
discovered factory instead of sent per-request.

## Alternatives considered

- **Config-driven over HTTP (status quo)** — passed over: no framework
  support for dynamic tool construction from strings, would require
  building an exec/compile sandbox ourselves (security surface), and adds
  friction for a Python-fluent target audience for no real benefit.
- **Explicit registration call** (`inspector.register(agent)` inside the
  user's script) — passed over: pulls `agent-inspector` in as a runtime
  import dependency of the user's own code. A dev tool that inspects code
  shouldn't need to be imported *by* that code.
- **MCP-Inspector-style subprocess + protocol** — passed over: there's no
  existing wire protocol for "what does this `LLMAgent` expose," so this
  would mean inventing one from scratch for no benefit over an in-process
  import, since both sides are already Python in the same process.

## Consequences

- Removes the need for #8's exec/compile tool-building problem entirely —
  tools are just real Python functions in the user's script, same as any
  other `llm-agents-from-scratch` usage.
- #8, #9 (skills), and #10 (model settings) need to be rescoped around
  "read from the discovered factory's `LLMAgent`" instead of "build from
  HTTP config" — most of their acceptance criteria (surfacing tools/skills
  in responses, validating the model) still apply, just sourced
  differently.
- `CreateSessionRequest` becomes a breaking change (shrinks to `{task}`);
  acceptable pre-1.0, but worth doing as one deliberate pass across M2
  rather than incrementally.
- New surface area this ADR doesn't resolve: how the CLI is actually
  pointed at a script (flag/argument shape), what happens on import
  errors or a missing/malformed factory (must fail with a clear message,
  not a stack trace), and whether a script can expose more than one named
  agent. These are implementation details for the M2 issue(s) that pick
  this up, not blocking this decision.
- Sessions no longer support truly dynamic per-request tool/skill
  variation (a client can't ask for a different tool set than what the
  script's factory builds) — acceptable, since that was never something
  M1 actually implemented beyond `next_number` regardless.

## References

- Issue #8 (function-tool registration), #9 (skills scope), #10 (model
  settings) — M2, need rescoping against this decision.
- [ADR-001](ADR-001-in-memory-single-process-session-store.md) — the
  single-process constraint this builds on (a discovered factory is
  called once per session, all within the same process).
- `docs/overview.md` — once implemented, add a short section describing
  the discovery mechanism as shipped, pointing back here for the *why*.
