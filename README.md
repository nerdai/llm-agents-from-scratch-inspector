# Agent Inspector

A dev tool for manually driving [`llm-agents-from-scratch`](https://github.com/nerdai/llm-agents-from-scratch)'s
`LLMAgent.SupervisedTaskHandler` one call at a time, over HTTP, via a React
frontend.

This repo is a two-language monorepo (Python backend + TypeScript
frontend) packaged as a single PyPI wheel that bundles the built frontend
assets and ships a CLI.

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
