<!-- markdownlint-disable-file MD024 -->

# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## Unreleased

- ...

## [0.1.1] - 2026-07-18

### Added

- docs: document `pip install` + bring-your-own-`agent_builder` usage in README (#77)

### Changed

- fix: recenter the favicon glyph within its square canvas; center `SupervisedTaskHandler` in the app bar (#79)
- fix: use `llm-agents-from-scratch`'s favicon as the browser-tab icon and app-bar logo, replacing the placeholder purple "A" badge (#78)

## [0.1.0.post1] - 2026-07-17

### Changed

- fix: attach `dist/*` (wheel + sdist) to the GitHub release — `release_github` and `deploy` run on separate runners with no shared filesystem, so the artifact glob never matched anything (#75)

## [0.1.0] - 2026-07-17

Initial public release.

### Added

- feat: repo scaffold — package layout, CLI, build hook (#35)
- feat: `SessionStore` + handler lifecycle (`SessionService`) (#36)
- feat: minimal React client — config, timeline, controls (#37)
- feat: implement session endpoints — create, next-step, run-step, complete (#45)
- feat: convention-based entrypoint discovery — `agent-inspector launch` imports a script's module-level `agent_builder` instead of building an agent from HTTP config (ADR-002) (#52)
- feat: implement `POST /api/sessions/{id}/reject` (#48)
- feat: implement `POST /api/sessions/{id}/abort` (#49)
- feat: implement `PATCH /api/sessions/{id}/step` (#50)
- feat: implement `PATCH /api/sessions/{id}/result` (#51)
- feat: surface real tools + `skills_scopes`/`explicit_only_skills` (#53)
- feat: implement read endpoints — rehydrate, rollout, templates (#54)
- feat: implement `GET /api/ollama/status` (#55)
- feat: shadcn/ui + Tailwind + TanStack Query foundation (#56)
- feat: add `demo.py` quickstart, porting `llm-agents-from-scratch`'s `ch08.ipynb` Example 3 (#57)
- feat: config rail (webapp layout) (#58)
- feat: two-operation timeline + artifact editing (#59)
- feat: reload rehydration — restore a session from `?session=` on load (#60)
- feat: templates + rollout drawers, approval gate, error toasts (#61)
- feat: port the prototype's warm palette + violet accent theme (#65)
- feat: evict idle sessions after a TTL, closing their MCP providers (#71)
- feat: concurrency guards + error surfaces — distinguish tool failures, shared exception handler (#72)

### Changed

- chore: pin `llm-agents-from-scratch` to the unreleased `SupervisedTaskHandler` commit (#38)
- chore: CI + pre-commit — lint Python (ruff/mypy) and TypeScript (eslint/prettier) (#39)
- docs: ADR-002 — convention-based entrypoint discovery (#46)
- fix: missing skill tool-call trace; pin `Controls`; add Abort button (#63)
- fix: stabilize `demo.py` — drop the `stop-at-one` skill from default discovery (#64)
- chore: move `docs/`/ADRs out of `.claude/` into a regular top-level `docs/` dir (#66)
- refactor: remove dead code — unused components and shadcn primitives (#68)
- refactor: extract a pluggable `SessionStore` interface behind `SessionService` (#69)
- chore: harden packaging CI — verify the wheel bundles the frontend, rename the PyPI distribution to `llm-agents-from-scratch-inspector` (#70)
- chore: add a checked-in Playwright E2E suite for the frontend (#73)
- fix: remove the redundant "step N" label from `run_step()` cards (#74)
