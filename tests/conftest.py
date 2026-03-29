"""Shared fixtures for Orchestra test suite."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.client import AgentResponse
from src.agents.definition import AgentRole


# ---------------------------------------------------------------------------
# AgentRole helpers
# ---------------------------------------------------------------------------

def make_role(
    name: str = "tester",
    display_name: str = "Tester",
    model: str = "haiku",
    system_prompt: str = "You are a test agent.",
    allowed_tools: list[str] | None = None,
    max_turns: int = 5,
) -> AgentRole:
    return AgentRole(
        name=name,
        display_name=display_name,
        model=model,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools or [],
        max_turns=max_turns,
    )


# ---------------------------------------------------------------------------
# AgentClient mock factory
# ---------------------------------------------------------------------------

def make_mock_client(
    name: str = "tester",
    display_name: str = "Tester",
    response_content: str = "Test response",
    cost: float = 0.01,
    is_error: bool = False,
    error_message: str = "",
) -> MagicMock:
    """Return a MagicMock that looks like AgentClient."""
    client = MagicMock()
    client.name = name
    client.display_name = display_name
    response = AgentResponse(
        agent_name=display_name,
        content=response_content,
        cost=cost,
        duration_ms=100,
        is_error=is_error,
        error_message=error_message,
    )
    client.run = AsyncMock(return_value=response)
    return client


@pytest.fixture
def mock_client():
    return make_mock_client()


@pytest.fixture
def mock_client_error():
    return make_mock_client(
        is_error=True,
        error_message="Connection refused",
        response_content="",
    )
