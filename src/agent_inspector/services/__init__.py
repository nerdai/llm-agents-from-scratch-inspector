"""Business-logic services for Agent Inspector.

This package is the only place domain/business logic lives. Routes
(``routes/``) call into services through the dependency-injected
instances declared in ``deps.py``; services raise domain exceptions
(``agent_inspector.errors``) rather than ``fastapi.HTTPException``,
leaving HTTP-status mapping to the route layer.

One module per domain concern:
    * ``health.py`` -- ``HealthService`` (see #1).
    * ``session.py`` -- ``SessionService`` (see #2), the in-memory
      ``SessionStore`` foundation that owns the live ``LLMAgent`` +
      ``SupervisedTaskHandler`` per session, the per-session busy
      lock, and the server-authoritative ``need`` state machine.
      Actual session creation (constructing an ``LLMAgent`` and
      calling ``run_supervised()``) and the step/approve/reject/abort
      orchestration that drives the ``need`` machine are wired up by
      later issues (#3-#6, #11-#14); this module only supplies the
      storage/lifecycle machinery they build on.

Import from the specific submodule (e.g.
``from agent_inspector.services.session import SessionService``)
rather than this package's ``__init__`` -- it intentionally re-exports
nothing, so it's always unambiguous which module a given service lives
in.
"""
