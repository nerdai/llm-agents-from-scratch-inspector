"""Custom hatchling build hook for bundling the frontend into the wheel.

Runs ``npm run build`` in ``frontend/`` and copies the resulting
``frontend/dist/`` directory to ``src/agent_inspector/web/`` before the
wheel's file set is determined, so the built assets are packaged
alongside the Python backend.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FrontendBuildHook(BuildHookInterface):  # type: ignore[misc]
    """Builds the Vite/React frontend and stages it under ``web/``."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Build the frontend and copy its assets into the package.

        Args:
            version (str): The build target version (unused).
            build_data (dict[str, Any]): Mutable build metadata (unused).
        """
        root = Path(self.root)
        frontend_dir = root / "frontend"
        web_dir = root / "src" / "agent_inspector" / "web"

        if not frontend_dir.is_dir():
            # Nothing to build (e.g. sdist-only environments); leave any
            # existing web/ directory untouched.
            return

        npm = shutil.which("npm")
        if npm is None:
            print(
                "[agent-inspector] npm not found on PATH; skipping "
                "frontend build. The wheel will be built without bundled "
                "UI assets.",
            )
            return

        print("[agent-inspector] Installing frontend dependencies...")
        subprocess.run(
            [npm, "install"],
            cwd=frontend_dir,
            check=True,
        )

        print("[agent-inspector] Building frontend...")
        subprocess.run(
            [npm, "run", "build"],
            cwd=frontend_dir,
            check=True,
        )

        dist_dir = frontend_dir / "dist"
        if not dist_dir.is_dir():
            raise RuntimeError(
                "Frontend build did not produce a dist/ directory at "
                f"{dist_dir}.",
            )

        if web_dir.exists():
            shutil.rmtree(web_dir)
        shutil.copytree(dist_dir, web_dir)
        print(f"[agent-inspector] Copied {dist_dir} -> {web_dir}")
