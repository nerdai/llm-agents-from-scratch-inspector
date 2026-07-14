"""Domain exceptions for Agent Inspector.

One module per domain concern, mirroring ``services/``:
    * ``session.py`` -- exceptions ``services/session.py`` raises.
      Framework-agnostic by design: nothing in ``services/`` may
      import FastAPI, so these are plain ``Exception`` subclasses;
      it's ``routes/``'s job to catch them and translate them into
      ``HTTPException``s -- each docstring notes the status code that
      mapping should use.
    * ``discovery.py`` -- exceptions ``discovery.py`` raises while
      importing a user's entrypoint script and locating their
      ``LLMAgentBuilder`` (see ADR-002). A startup-time (``cli.py``)
      concern, not a per-request one -- these never reach the route
      layer, so they carry no HTTP-status mapping.

Import from the specific submodule (e.g.
``from agent_inspector.errors.session import SessionNotFoundError``)
rather than this package's ``__init__`` -- it intentionally re-exports
nothing, so it's always unambiguous which module an exception lives
in.
"""
