"""Business-logic services for Agent Inspector.

This module is the only place domain/business logic lives. Routes
(``routes.py``) call into services through the dependency-injected
instances declared in ``deps.py``; services raise domain exceptions
rather than ``fastapi.HTTPException``, leaving HTTP-status mapping to
the route layer.

NOTE: This currently contains only a trivial ``HealthService`` to
establish the services -> deps -> routes -> server layering. The real
``SessionService`` (owning the ``SessionStore`` and all
``SupervisedTaskHandler`` orchestration) is added in a later issue.
"""


class HealthService:
    """Reports whether the backend process is up and responsive."""

    def check(self) -> dict[str, str]:
        """Return the current liveness status of the backend.

        Returns:
            dict[str, str]: A status payload, e.g. ``{"status": "ok"}``.
        """
        return {"status": "ok"}
