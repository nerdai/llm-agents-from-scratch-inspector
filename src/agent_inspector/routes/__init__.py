"""API route registration.

Routes are intentionally thin: parse the request, call the relevant
service via its injected dependency, map any domain exception to an
appropriate ``HTTPException``, and return. No business logic lives
here -- see ``services/``.

One module per domain concern, mirroring ``services/`` (e.g.
``health.py`` here pairs with ``services/health.py``); this package's
``router`` combines each submodule's routes under the shared ``/api``
prefix.
"""

from fastapi import APIRouter

from agent_inspector.routes import health

router = APIRouter(prefix="/api")
router.include_router(health.router)
