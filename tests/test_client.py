"""Tests for agents/client.py — AgentResponse, AgentClient."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.agents.client import AgentClient, AgentResponse
from src.agents.definition import AgentRole

try:
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
    HAS_SDK = True
except ImportError:
    HAS_SDK = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_role(**kwargs) -> AgentRole:
    defaults = dict(
        name="tester",
        display_name="Tester",
        model="haiku",
        system_prompt="You are a test agent.",
        allowed_tools=[],
        max_turns=5,
    )
    defaults.update(kwargs)
    return AgentRole(**defaults)


def make_text_block(text: str):
    b = MagicMock(spec=TextBlock)
    b.text = text
    return b


def make_tool_use_block(name: str):
    b = MagicMock(spec=ToolUseBlock)
    b.name = name
    return b


def make_assistant_message(blocks):
    msg = MagicMock(spec=AssistantMessage)
    msg.content = blocks
    return msg


def make_result_message(result="Final answer", session_id="sess_001", cost=0.05, num_turns=3):
    msg = MagicMock(spec=ResultMessage)
    msg.result = result
    msg.session_id = session_id
    msg.total_cost_usd = cost
    msg.num_turns = num_turns
    return msg


# ---------------------------------------------------------------------------
# AgentResponse
# ---------------------------------------------------------------------------

class TestAgentResponse:
    def test_defaults(self):
        r = AgentResponse(agent_name="Alice", content="Hello")
        assert r.session_id == ""
        assert r.cost == 0.0
        assert r.duration_ms == 0
        assert r.num_turns == 0
        assert r.tools_used == []
        assert r.is_error is False
        assert r.error_message == ""

    def test_error_response(self):
        r = AgentResponse(
            agent_name="Alice", content="", is_error=True, error_message="Boom"
        )
        assert r.is_error is True
        assert r.error_message == "Boom"


# ---------------------------------------------------------------------------
# AgentClient construction
# ---------------------------------------------------------------------------

class TestAgentClientInit:
    def test_name_from_role(self):
        role = make_role(name="dev", display_name="Developer")
        with patch("src.agents.client.get_session", return_value=None):
            client = AgentClient(role)
        assert client.name == "dev"
        assert client.display_name == "Developer"

    def test_default_project_path_is_cwd(self):
        role = make_role()
        with patch("src.agents.client.get_session", return_value=None):
            client = AgentClient(role)
        assert client.project_path == Path.cwd()

    def test_custom_project_path(self, tmp_path):
        role = make_role()
        with patch("src.agents.client.get_session", return_value=None):
            client = AgentClient(role, project_path=tmp_path)
        assert client.project_path == tmp_path

    def test_loads_existing_session(self):
        role = make_role(name="dev")
        with patch("src.agents.client.get_session", return_value="existing_sess") as mock_get:
            client = AgentClient(role)
        mock_get.assert_called_once_with("dev")
        assert client._session_id == "existing_sess"

    def test_no_existing_session(self):
        role = make_role(name="dev")
        with patch("src.agents.client.get_session", return_value=None):
            client = AgentClient(role)
        assert client._session_id is None


# ---------------------------------------------------------------------------
# _build_options
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_SDK, reason="claude_agent_sdk not installed")
class TestBuildOptions:
    def _make_client(self, **role_kwargs) -> AgentClient:
        role = make_role(**role_kwargs)
        with patch("src.agents.client.get_session", return_value=None):
            return AgentClient(role)

    def test_system_prompt_set(self):
        client = self._make_client(system_prompt="Be helpful.")
        opts = client._build_options("Be helpful.")
        assert opts.system_prompt == "Be helpful."

    def test_model_from_role(self):
        client = self._make_client(model="opus")
        opts = client._build_options("prompt")
        assert opts.model == "opus"

    def test_allowed_tools_none_when_empty(self):
        client = self._make_client(allowed_tools=[])
        opts = client._build_options("prompt")
        assert opts.allowed_tools is None

    def test_allowed_tools_set_when_provided(self):
        client = self._make_client(allowed_tools=["Read", "Write"])
        opts = client._build_options("prompt")
        assert opts.allowed_tools == ["Read", "Write"]

    def test_max_turns_from_role(self):
        client = self._make_client(max_turns=10)
        opts = client._build_options("prompt")
        assert opts.max_turns == 10

    def test_permission_mode_bypass(self):
        client = self._make_client()
        opts = client._build_options("prompt")
        assert opts.permission_mode == "bypassPermissions"

    def test_resume_set_when_session_exists(self):
        role = make_role()
        with patch("src.agents.client.get_session", return_value="sess_xyz"):
            client = AgentClient(role)
        opts = client._build_options("prompt")
        assert opts.resume == "sess_xyz"

    def test_resume_not_set_when_no_session(self):
        client = self._make_client()
        opts = client._build_options("prompt")
        assert not hasattr(opts, "resume") or opts.resume is None or opts.resume == ""

    def test_cli_path_set_when_provided(self):
        role = make_role()
        with patch("src.agents.client.get_session", return_value=None):
            client = AgentClient(role, cli_path="/usr/bin/claude")
        opts = client._build_options("prompt")
        assert opts.cli_path == "/usr/bin/claude"


# ---------------------------------------------------------------------------
# _extract_text
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_SDK, reason="claude_agent_sdk not installed")
class TestExtractText:
    def _make_client(self) -> AgentClient:
        with patch("src.agents.client.get_session", return_value=None):
            return AgentClient(make_role())

    def test_single_text_block(self):
        client = self._make_client()
        msg = make_assistant_message([make_text_block("Hello")])
        assert client._extract_text(msg) == "Hello"

    def test_multiple_text_blocks_joined(self):
        client = self._make_client()
        msg = make_assistant_message([
            make_text_block("Part 1"),
            make_text_block("Part 2"),
        ])
        assert client._extract_text(msg) == "Part 1\nPart 2"

    def test_ignores_non_text_blocks(self):
        client = self._make_client()
        msg = make_assistant_message([
            make_tool_use_block("Read"),
            make_text_block("Some text"),
        ])
        assert client._extract_text(msg) == "Some text"

    def test_empty_content(self):
        client = self._make_client()
        msg = make_assistant_message([])
        assert client._extract_text(msg) == ""

    def test_none_content(self):
        client = self._make_client()
        msg = MagicMock(spec=AssistantMessage)
        msg.content = None
        assert client._extract_text(msg) == ""


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_SDK, reason="claude_agent_sdk not installed")
class TestParseResponse:
    def _make_client(self) -> AgentClient:
        with patch("src.agents.client.get_session", return_value=None):
            return AgentClient(make_role(name="dev"))

    def test_result_message_preferred_for_content(self):
        client = self._make_client()
        msgs = [
            make_assistant_message([make_text_block("Intermediate")]),
            make_result_message(result="Final answer"),
        ]
        with patch("src.agents.client.set_session"):
            resp = client._parse_response(msgs, start=0.0)
        assert resp.content == "Final answer"

    def test_cost_from_result_message(self):
        client = self._make_client()
        msgs = [make_result_message(cost=0.123)]
        with patch("src.agents.client.set_session"):
            resp = client._parse_response(msgs, start=0.0)
        assert resp.cost == pytest.approx(0.123)

    def test_num_turns_from_result_message(self):
        client = self._make_client()
        msgs = [make_result_message(num_turns=7)]
        with patch("src.agents.client.set_session"):
            resp = client._parse_response(msgs, start=0.0)
        assert resp.num_turns == 7

    def test_session_id_from_result_message(self):
        client = self._make_client()
        msgs = [make_result_message(session_id="sess_abc")]
        with patch("src.agents.client.set_session") as mock_set:
            resp = client._parse_response(msgs, start=0.0)
        assert resp.session_id == "sess_abc"
        mock_set.assert_called_once_with("dev", "sess_abc")

    def test_session_stored_on_client(self):
        client = self._make_client()
        msgs = [make_result_message(session_id="sess_xyz")]
        with patch("src.agents.client.set_session"):
            client._parse_response(msgs, start=0.0)
        assert client._session_id == "sess_xyz"

    def test_tools_collected_from_assistant_messages(self):
        client = self._make_client()
        msgs = [
            make_assistant_message([make_tool_use_block("Read"), make_tool_use_block("Write")]),
            make_result_message(result="done"),
        ]
        with patch("src.agents.client.set_session"):
            resp = client._parse_response(msgs, start=0.0)
        assert "Read" in resp.tools_used
        assert "Write" in resp.tools_used

    def test_fallback_to_assistant_content_when_no_result_text(self):
        client = self._make_client()
        result_msg = make_result_message(result=None)
        asst_msg = make_assistant_message([make_text_block("Only this")])
        with patch("src.agents.client.set_session"):
            resp = client._parse_response([asst_msg, result_msg], start=0.0)
        assert "Only this" in resp.content

    def test_empty_messages_gives_empty_response(self):
        client = self._make_client()
        with patch("src.agents.client.set_session"):
            resp = client._parse_response([], start=0.0)
        assert resp.content == ""
        assert resp.cost == 0.0

    def test_agent_name_is_display_name(self):
        role = make_role(display_name="My Agent")
        with patch("src.agents.client.get_session", return_value=None):
            client = AgentClient(role)
        with patch("src.agents.client.set_session"):
            resp = client._parse_response([], start=0.0)
        assert resp.agent_name == "My Agent"


# ---------------------------------------------------------------------------
# run() — full integration with mocked SDK
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_SDK, reason="claude_agent_sdk not installed")
class TestRun:
    def _make_client(self, **role_kwargs) -> AgentClient:
        with patch("src.agents.client.get_session", return_value=None):
            return AgentClient(make_role(**role_kwargs))

    def _make_sdk_client(self, messages: list):
        """Return a mock ClaudeSDKClient that yields the given messages."""
        sdk = MagicMock()
        sdk.connect = AsyncMock()
        sdk.disconnect = AsyncMock()
        sdk.query = AsyncMock()

        async def receive_messages():
            for msg in messages:
                yield msg

        sdk.receive_messages = receive_messages
        return sdk

    async def test_returns_agent_response(self):
        client = self._make_client()
        msgs = [make_result_message(result="Answer")]
        sdk = self._make_sdk_client(msgs)

        with patch("src.agents.client.ClaudeSDKClient", return_value=sdk), \
             patch("src.agents.client.set_session"):
            resp = await client.run("Do something")

        assert isinstance(resp, AgentResponse)
        assert resp.content == "Answer"
        assert not resp.is_error

    async def test_connects_and_disconnects(self):
        client = self._make_client()
        sdk = self._make_sdk_client([make_result_message()])

        with patch("src.agents.client.ClaudeSDKClient", return_value=sdk), \
             patch("src.agents.client.set_session"):
            await client.run("task")

        sdk.connect.assert_called_once()
        sdk.disconnect.assert_called_once()

    async def test_disconnects_on_exception(self):
        client = self._make_client()
        sdk = MagicMock()
        sdk.connect = AsyncMock()
        sdk.disconnect = AsyncMock()
        sdk.query = AsyncMock(side_effect=RuntimeError("Network error"))

        with patch("src.agents.client.ClaudeSDKClient", return_value=sdk):
            resp = await client.run("task")

        sdk.disconnect.assert_called_once()
        assert resp.is_error
        assert "Network error" in resp.error_message

    async def test_context_prefix_prepended_to_system_prompt(self):
        client = self._make_client(system_prompt="Base prompt.")
        captured_opts = []

        def capture_opts(opts):
            captured_opts.append(opts)
            sdk = MagicMock()
            sdk.connect = AsyncMock()
            sdk.disconnect = AsyncMock()
            sdk.query = AsyncMock()

            async def recv():
                yield make_result_message()

            sdk.receive_messages = recv
            return sdk

        with patch("src.agents.client.ClaudeSDKClient", side_effect=capture_opts), \
             patch("src.agents.client.set_session"):
            await client.run("task", context_prefix="Context here.")

        assert len(captured_opts) == 1
        assert "Context here." in captured_opts[0].system_prompt
        assert "Base prompt." in captured_opts[0].system_prompt

    async def test_on_stream_called_for_assistant_messages(self):
        client = self._make_client()
        streamed = []

        async def on_stream(name, text):
            streamed.append((name, text))

        msgs = [
            make_assistant_message([make_text_block("streaming chunk")]),
            make_result_message(result="done"),
        ]
        sdk = self._make_sdk_client(msgs)

        with patch("src.agents.client.ClaudeSDKClient", return_value=sdk), \
             patch("src.agents.client.set_session"):
            await client.run("task", on_stream=on_stream)

        assert any("streaming chunk" in t for _, t in streamed)

    async def test_exception_returns_error_response(self):
        client = self._make_client()
        sdk = MagicMock()
        sdk.connect = AsyncMock(side_effect=ConnectionError("refused"))
        sdk.disconnect = AsyncMock()

        with patch("src.agents.client.ClaudeSDKClient", return_value=sdk):
            resp = await client.run("task")

        assert resp.is_error
        assert "refused" in resp.error_message
        assert resp.content == ""
