# Agent Inspector

A dev tool for manually driving [`llm-agents-from-scratch`](https://github.com/nerdai/llm-agents-from-scratch)'s
`LLMAgent.SupervisedTaskHandler` one call at a time, over HTTP, via a React
frontend.

This repo is a two-language monorepo (Python backend + TypeScript
frontend) packaged as a single PyPI wheel that bundles the built frontend
assets and ships a CLI.

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
