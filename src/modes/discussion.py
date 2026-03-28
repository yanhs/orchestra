"""Discussion mode — parallel debate between agents."""

import asyncio
from typing import Any

from ..agents.client import AgentClient, AgentResponse
from ..orchestrator.transcript import Transcript
from .base import BaseMode, OrchestraResult, UpdateCallback


class DiscussionMode(BaseMode):
    """Parallel discussion between agents.

    Within each round, all agents work simultaneously.
    Between rounds, each agent sees the full transcript from previous rounds.
    After all rounds, an optional summarizer produces a final summary.
    """

    def __init__(
        self,
        max_rounds: int = 2,
        summarizer: AgentClient | None = None,
    ):
        self.max_rounds = max_rounds
        self.summarizer = summarizer

    async def execute(
        self,
        topic: str,
        agents: list[AgentClient],
        on_update: UpdateCallback | None = None,
        **kwargs: Any,
    ) -> OrchestraResult:
        result = OrchestraResult(mode="discussion", topic=topic)
        transcript = Transcript()

        for round_num in range(1, self.max_rounds + 1):
            # Notify all agents starting
            if on_update:
                for agent in agents:
                    r = on_update(
                        agent.display_name,
                        "start",
                        f"Round {round_num}/{self.max_rounds}",
                    )
                    if asyncio.iscoroutine(r):
                        await r

            # All agents work in parallel within a round
            async def run_agent(agent: AgentClient) -> tuple[AgentClient, AgentResponse]:
                prompt = self._build_prompt(topic, transcript, agent, round_num)
                response = await agent.run(prompt)
                return agent, response

            responses = await asyncio.gather(
                *[run_agent(a) for a in agents]
            )

            # Collect results
            for agent, response in responses:
                if response.is_error:
                    if on_update:
                        r = on_update(agent.display_name, "error", response.error_message)
                        if asyncio.iscoroutine(r):
                            await r
                    continue

                transcript.add(agent.display_name, response.content)
                result.add_response(response)

                if on_update:
                    r = on_update(agent.display_name, "done", response.content)
                    if asyncio.iscoroutine(r):
                        await r

            transcript.next_round()

        # Summarize
        if self.summarizer:
            if on_update:
                r = on_update(self.summarizer.display_name, "start", "Summarizing")
                if asyncio.iscoroutine(r):
                    await r

            summary_prompt = self._build_summary_prompt(topic, transcript)
            summary_response = await self.summarizer.run(summary_prompt)

            if not summary_response.is_error:
                result.summary = summary_response.content
                result.add_response(summary_response)

            if on_update:
                r = on_update(self.summarizer.display_name, "done", result.summary)
                if asyncio.iscoroutine(r):
                    await r

        return result

    def _build_prompt(
        self,
        topic: str,
        transcript: Transcript,
        agent: AgentClient,
        round_num: int,
    ) -> str:
        parts = [f"## Discussion Topic\n{topic}"]

        if transcript.entries:
            parts.append(f"## Previous Responses\n{transcript.format()}")

        if round_num == 1:
            parts.append(
                f"Share your perspective on this topic as {agent.display_name}. "
                "Be concise and specific."
            )
        else:
            parts.append(
                f"This is round {round_num}. Review the discussion above and add "
                "new insights, respond to other perspectives, or refine your position. "
                "Don't repeat what's already been said."
            )

        return "\n\n".join(parts)

    def _build_summary_prompt(self, topic: str, transcript: Transcript) -> str:
        return (
            f"## Discussion Topic\n{topic}\n\n"
            f"## Full Discussion\n{transcript.format()}\n\n"
            "## Your Task\n"
            "Summarize this discussion. Structure your summary as:\n"
            "1. **Key decisions / agreements** — what the team aligned on\n"
            "2. **Open questions / disagreements** — unresolved points\n"
            "3. **Action items** — concrete next steps\n\n"
            "Be concise. Use bullet points."
        )
