# Agent Inspector

A dev tool for manually driving [`llm-agents-from-scratch`](https://github.com/nerdai/llm-agents-from-scratch)'s
`LLMAgent.SupervisedTaskHandler` one call at a time, over HTTP, via a React
frontend.

This repo is a two-language monorepo (Python backend + TypeScript
frontend) packaged as a single PyPI wheel that bundles the built frontend
assets and ships a CLI.

## Installation

```bash
pip install llm-agents-from-scratch-inspector
```

This installs the `agent-inspector` CLI and pulls in
`llm-agents-from-scratch` as a dependency. (The PyPI distribution name
differs from the CLI command and the importable package,
`agent_inspector`, only because the short name was already taken on
PyPI.) If you're working from a clone of this repo instead, use
`uv sync` — see [Development](#development) below.

## Using your own agent

`agent-inspector launch` doesn't build an agent from flags or a config
file — it imports a Python script you write and looks for a
module-level `agent_builder`: an `LLMAgentBuilder`
(`llm_agents_from_scratch`) with at least `.with_llm(...)` called on
it, following the same fluent `with_*` pattern (`.with_tool(...)`,
`.with_skill(...)`, `.with_memory(...)`, ...) you'd use anywhere else
in the framework.

```python
# main.py
from llm_agents_from_scratch import LLMAgentBuilder
from llm_agents_from_scratch.data_structures import Task
from llm_agents_from_scratch.llms import OllamaLLM

agent_builder = (
    LLMAgentBuilder()
    .with_llm(OllamaLLM(model="qwen3:14b"))
    .with_tool(my_tool)
)

# Optional -- pre-fills the UI's task field at launch time.
default_task = Task(instruction="Describe the task to run by default.")
```

```bash
ollama serve                    # in one terminal, if using OllamaLLM
agent-inspector launch main.py  # in another
```

This opens a browser tab at the Inspector UI, where you can enter a
task and step through `get_next_step()`/`run_step()` against your own
agent instead of the bundled demo below. `demo.py` (used in the
Quickstart) is itself just an `agent_builder` script following this
same convention — see `docs/overview.md`'s "Entrypoint discovery"
section ([ADR-002](docs/adr/ADR-002-convention-based-entrypoint-discovery.md))
for the full mechanism.

If `launch` fails, the error is meant to tell you exactly what's
wrong rather than a bare traceback:

| Error                          | Likely cause                                                        |
|---------------------------------|-----------------------------------------------------------------------|
| script not found                | the path doesn't exist relative to your current directory             |
| error importing script          | the script itself raises — run `python main.py` directly to see why   |
| no `agent_builder` found        | the variable isn't named exactly `agent_builder`, or isn't at module scope |
| `agent_builder` has the wrong type | it isn't an `LLMAgentBuilder` instance                              |
| `agent_builder` isn't ready     | `.with_llm(...)` was never called on it before `launch` imports it    |
| `default_task` has the wrong type | it's present but isn't a `Task` instance                            |

Run `agent-inspector launch --help` for the full flag list (`--port`,
`--no-open`, `--session-ttl-seconds`, ...) — `--dev` and
`--backend-only` are for contributors working on this repo's own
frontend, not needed for a normal run.

## Quickstart

`demo.py` (repo root) is a ready-to-run `agent_builder` entrypoint --
a port of [`llm-agents-from-scratch`](https://github.com/nerdai/llm-agents-from-scratch)'s
`examples/ch08.ipynb` Example 3 (Hailstone sequence via a single
`next_number` tool), driven one call at a time through the Inspector's
UI instead of the notebook's own manual loop.

1. Install and start [Ollama](https://ollama.com/download), then pull the
   model `demo.py` uses:

   ```bash
   ollama serve                 # in one terminal
   ollama pull qwen3:14b        # in another
   ```

2. From this repo's root:

   ```bash
   uv sync
   uv run agent-inspector launch demo.py
   ```

   This opens a browser tab. Enter a task, e.g. "Compute the full
   Hailstone sequence starting from 4, step by step using
   next_number, until you reach 1.", create the session, and step
   through `get_next_step()`/`run_step()` until the agent reaches a
   final result to approve.

No local Ollama? `demo_cloud.py` is the same demo pointed at
[Ollama Cloud](https://ollama.com/cloud) instead -- set `OLLAMA_API_KEY`
(the `ollama` package reads it directly; nothing here handles it) and
run `uv run agent-inspector launch demo_cloud.py`. The app bar shows
an "ollama cloud" chip instead of the local daemon's online/offline
check either way.

## Development

`agent-inspector launch` takes a path to a Python script that exposes an
`agent_builder` (an `LLMAgentBuilder` instance) at module scope -- see
`docs/overview.md`'s "Entrypoint discovery" section for the full
convention:

```bash
uv sync
uv run agent-inspector launch main.py --dev
```

See `frontend/` for the React/Vite UI and `src/agent_inspector/` for the
FastAPI backend and CLI.

### Testing

```bash
make test-backend    # pytest, backend only
make test-frontend   # Playwright E2E, frontend + a real backend
make test            # both
```

`test-frontend` runs the checked-in suite under `frontend/e2e/` --
first time, install the browser binaries Playwright needs:

```bash
cd frontend && npx playwright install --with-deps chromium
```

The suite drives a real `agent-inspector launch` instance end to end
(no mocking), but needs no live Ollama daemon: `frontend/e2e/fixtures/
scripted_agent.py` is a network-free `agent_builder` backed by a
scripted `BaseLLM`, started automatically by `playwright.config.ts`'s
`webServer`. Nothing needs to be running beforehand.
