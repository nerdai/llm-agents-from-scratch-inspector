# Agent Inspector

A dev tool for manually driving [`llm-agents-from-scratch`](https://github.com/nerdai/llm-agents-from-scratch)'s
`LLMAgent.SupervisedTaskHandler` one call at a time, over HTTP, via a React
frontend.

This repo is a two-language monorepo (Python backend + TypeScript
frontend) packaged as a single PyPI wheel that bundles the built frontend
assets and ships a CLI.

## Development

```bash
uv sync
uv run agent-inspector launch --dev
```

See `frontend/` for the React/Vite UI and `src/agent_inspector/` for the
FastAPI backend and CLI.
