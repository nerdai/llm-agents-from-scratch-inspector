"""Tests for ``GET /api/templates`` (TRD §6.9, issue #15).

Not session-scoped -- exercises the route directly against a bare
``TestClient`` (no ``SessionService`` dependency override needed).
"""

from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient
from llm_agents_from_scratch.agent.templates import default_templates

from agent_inspector.server import create_app

_EXPECTED_TEMPLATE_COUNT = 11

_EXPECTED_KEYS = {
    "system_message",
    "get_next_step",
    "step_rollout_chat_message",
    "step_rollout_content_instruction",
    "step_rollout_content_tool_call_request",
    "run_step_system_message_without_rollout",
    "run_step_system_message",
    "run_step_user_message",
    "skills_catalog",
    "memories",
    "approval_rejection_feedback",
}


class TestGetTemplates:
    """``GET /api/templates`` (TRD §6.9)."""

    def test_templates_returns_all_eleven_keys(self) -> None:
        """All 11 ``LLMAgentTemplates`` keys are present, not a subset."""
        client = TestClient(create_app(serve_static=False))

        response = client.get("/api/templates")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert set(body.keys()) == _EXPECTED_KEYS
        assert len(body) == _EXPECTED_TEMPLATE_COUNT

    def test_templates_matches_framework_defaults(self) -> None:
        """Values match the framework's own ``default_templates`` exactly."""
        client = TestClient(create_app(serve_static=False))

        response = client.get("/api/templates")

        body = response.json()
        for key, expected_value in default_templates.items():
            assert body[key] == expected_value
