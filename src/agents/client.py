"""AgentClient — wrapper around ClaudeSDKClient for a single agent."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from ..orchestrator.sessions import get_session, set_session
from .definition import AgentRole


@dataclass
class AgentResponse:
    """Response from a single agent run."""

    agent_name: str
    content: str
    session_id: str = ""
    cost: float = 0.0
    duration_ms: int = 0
    num_turns: int = 0
    tools_used: list[str] = field(default_factory=list)
    is_error: bool = False
    error_message: str = ""


# Callback type: async fn(agent_name, text_chunk)
StreamCallback = Callable[[str, str], Any]


class AgentClient:
    """Wraps ClaudeSDKClient for a single agent role."""

    def __init__(
        self,
        role: AgentRole,
        project_path: Path | None = None,
        cli_path: str | None = None,
    ):
        self.role = role
        self.project_path = project_path or Path.cwd()
        self.cli_path = cli_path
        self._session_id: str | None = get_session(role.name)

    @property
    def name(self) -> str:
        return self.role.name

    @property
    def display_name(self) -> str:
        return self.role.display_name

    def _build_options(self, system_prompt: str) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions for this agent."""
        opts = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=self.role.model,
            allowed_tools=self.role.allowed_tools or None,
            max_turns=self.role.max_turns,
            cwd=str(self.project_path),
            permission_mode="bypassPermissions",
        )
        if self.cli_path:
            opts.cli_path = self.cli_path
        if self._session_id:
            opts.resume = self._session_id
        return opts

    async def run(
        self,
        prompt: str,
        context_prefix: str = "",
        on_stream: StreamCallback | None = None,
    ) -> AgentResponse:
        """Send prompt to agent and collect full response.

        Args:
            prompt: The task/message for the agent.
            context_prefix: Extra context prepended to the system prompt.
            on_stream: Optional async callback for streaming text chunks.
        """
        system_prompt = self.role.system_prompt
        if context_prefix:
            system_prompt = context_prefix + "\n\n" + system_prompt

        options = self._build_options(system_prompt)
        start = asyncio.get_event_loop().time()

        try:
            client = ClaudeSDKClient(options)
            messages = []

            try:
                await client.connect()
                await client.query(prompt)

                async for msg in client.receive_messages():
                    messages.append(msg)

                    if isinstance(msg, ResultMessage):
                        break

                    # Stream text chunks
                    if on_stream and isinstance(msg, AssistantMessage):
                        text = self._extract_text(msg)
                        if text:
                            result = on_stream(self.role.display_name, text)
                            if asyncio.iscoroutine(result):
                                await result
            finally:
                await client.disconnect()

            return self._parse_response(messages, start)

        except Exception as e:
            duration = int((asyncio.get_event_loop().time() - start) * 1000)
            return AgentResponse(
                agent_name=self.role.display_name,
                content="",
                duration_ms=duration,
                is_error=True,
                error_message=str(e),
            )

    def _extract_text(self, msg: AssistantMessage) -> str:
        """Extract text content from an AssistantMessage."""
        parts = []
        for block in msg.content or []:
            if isinstance(block, TextBlock):
                parts.append(block.text)
        return "\n".join(parts)

    def _parse_response(self, messages: list, start: float) -> AgentResponse:
        """Parse collected messages into AgentResponse."""
        duration = int((asyncio.get_event_loop().time() - start) * 1000)

        content_parts = []
        tools = []
        session_id = ""
        cost = 0.0
        num_turns = 0

        for msg in messages:
            if isinstance(msg, ResultMessage):
                session_id = getattr(msg, "session_id", "") or ""
                cost = getattr(msg, "total_cost_usd", 0.0) or 0.0
                num_turns = getattr(msg, "num_turns", 0) or 0
                # Prefer ResultMessage.result if available
                result_text = getattr(msg, "result", None)
                if result_text:
                    content_parts = [result_text]
            elif isinstance(msg, AssistantMessage):
                for block in msg.content or []:
                    if isinstance(block, TextBlock):
                        content_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tools.append(block.name)

        if session_id:
            self._session_id = session_id
            set_session(self.role.name, session_id)

        return AgentResponse(
            agent_name=self.role.display_name,
            content="\n".join(content_parts),
            session_id=session_id,
            cost=cost,
            duration_ms=duration,
            num_turns=num_turns,
            tools_used=tools,
        )
