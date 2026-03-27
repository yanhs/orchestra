"""Consensus mode — voting with structured output."""

import asyncio
import json
import re
from typing import Any

from ..agents.client import AgentClient, AgentResponse
from .base import BaseMode, OrchestraResult, UpdateCallback


class ConsensusMode(BaseMode):
    """Agents vote independently on a question. Supermajority decides.

    Each agent produces a structured vote: choice, confidence, reasoning.
    If no consensus after max_rounds, the result includes the split.
    """

    def __init__(
        self,
        threshold: float = 0.67,
        max_rounds: int = 3,
    ):
        self.threshold = threshold
        self.max_rounds = max_rounds

    async def execute(
        self,
        topic: str,
        agents: list[AgentClient],
        on_update: UpdateCallback | None = None,
        **kwargs: Any,
    ) -> OrchestraResult:
        result = OrchestraResult(mode="consensus", topic=topic)
        all_votes: list[dict] = []
        previous_round_summary = ""

        for round_num in range(1, self.max_rounds + 1):
            round_votes: list[dict] = []

            if on_update:
                r = on_update("Consensus", "start", f"Round {round_num}/{self.max_rounds}")
                if asyncio.iscoroutine(r):
                    await r

            # All agents vote concurrently
            async def collect_vote(agent: AgentClient) -> tuple[AgentClient, AgentResponse]:
                prompt = self._build_vote_prompt(topic, round_num, previous_round_summary)
                response = await agent.run(prompt)
                return agent, response

            vote_results = await asyncio.gather(
                *[collect_vote(a) for a in agents]
            )

            for agent, response in vote_results:
                result.add_response(response)

                if response.is_error:
                    if on_update:
                        r = on_update(agent.display_name, "error", response.error_message)
                        if asyncio.iscoroutine(r):
                            await r
                    continue

                vote = self._parse_vote(agent.display_name, response.content)
                round_votes.append(vote)
                all_votes.append(vote)

                if on_update:
                    r = on_update(
                        agent.display_name,
                        "done",
                        f"Vote: {vote['choice']} (confidence: {vote['confidence']})",
                    )
                    if asyncio.iscoroutine(r):
                        await r

            # Check consensus
            consensus = self._check_consensus(round_votes)
            if consensus:
                result.summary = self._format_result(
                    consensus, round_votes, round_num, agreed=True
                )
                if on_update:
                    r = on_update("Consensus", "done", result.summary)
                    if asyncio.iscoroutine(r):
                        await r
                return result

            # Prepare context for next round
            previous_round_summary = self._format_round(round_votes, round_num)

        # No consensus reached
        result.summary = self._format_result(
            self._get_leading_choice(all_votes),
            all_votes,
            self.max_rounds,
            agreed=False,
        )
        if on_update:
            r = on_update("Consensus", "done", result.summary)
            if asyncio.iscoroutine(r):
                await r

        return result

    def _build_vote_prompt(
        self, topic: str, round_num: int, previous_summary: str
    ) -> str:
        parts = [
            f"## Decision Question\n{topic}",
        ]

        if previous_summary:
            parts.append(f"## Previous Round Results\n{previous_summary}")
            parts.append(
                "Consider the other perspectives above. "
                "You may change your vote or strengthen your position."
            )

        parts.append(
            "## Your Vote\n"
            "Respond with EXACTLY this format:\n\n"
            "CHOICE: <your choice — a short label>\n"
            "CONFIDENCE: <0.0 to 1.0>\n"
            "REASONING: <2-3 sentences explaining why>\n\n"
            "Be decisive. Pick one option."
        )

        return "\n\n".join(parts)

    def _parse_vote(self, agent_name: str, content: str) -> dict:
        """Parse structured vote from agent response."""
        choice = ""
        confidence = 0.5
        reasoning = ""

        for line in content.split("\n"):
            line_stripped = line.strip()
            if line_stripped.upper().startswith("CHOICE:"):
                choice = line_stripped.split(":", 1)[1].strip()
            elif line_stripped.upper().startswith("CONFIDENCE:"):
                try:
                    confidence = float(
                        re.search(r"[\d.]+", line_stripped.split(":", 1)[1]).group()
                    )
                except (AttributeError, ValueError):
                    confidence = 0.5
            elif line_stripped.upper().startswith("REASONING:"):
                reasoning = line_stripped.split(":", 1)[1].strip()

        # Fallback: if no structured format, use entire content as reasoning
        if not choice:
            choice = content.split("\n")[0][:80].strip()
            reasoning = content[:300]

        return {
            "agent": agent_name,
            "choice": choice,
            "confidence": min(max(confidence, 0.0), 1.0),
            "reasoning": reasoning,
        }

    def _check_consensus(self, votes: list[dict]) -> str | None:
        """Check if any choice has supermajority."""
        if not votes:
            return None

        choice_counts: dict[str, int] = {}
        for v in votes:
            key = v["choice"].lower().strip()
            choice_counts[key] = choice_counts.get(key, 0) + 1

        total = len(votes)
        for choice, count in choice_counts.items():
            if count / total >= self.threshold:
                # Return original casing from first vote with this choice
                for v in votes:
                    if v["choice"].lower().strip() == choice:
                        return v["choice"]
        return None

    def _get_leading_choice(self, votes: list[dict]) -> str:
        """Get the choice with the most votes."""
        choice_counts: dict[str, int] = {}
        for v in votes:
            key = v["choice"].lower().strip()
            choice_counts[key] = choice_counts.get(key, 0) + 1

        leading = max(choice_counts, key=choice_counts.get)
        for v in votes:
            if v["choice"].lower().strip() == leading:
                return v["choice"]
        return leading

    def _format_round(self, votes: list[dict], round_num: int) -> str:
        lines = [f"### Round {round_num} Votes:"]
        for v in votes:
            lines.append(
                f"- **{v['agent']}**: {v['choice']} "
                f"(confidence: {v['confidence']}) — {v['reasoning']}"
            )
        return "\n".join(lines)

    def _format_result(
        self, winner: str, votes: list[dict], rounds: int, agreed: bool
    ) -> str:
        status = "CONSENSUS REACHED" if agreed else "NO CONSENSUS"
        lines = [
            f"## {status} (after {rounds} round{'s' if rounds > 1 else ''})",
            f"**Decision: {winner}**" if agreed else f"**Leading choice: {winner}** (below threshold)",
            "",
            "### Vote Breakdown:",
        ]
        for v in votes:
            lines.append(
                f"- {v['agent']}: **{v['choice']}** "
                f"(confidence: {v['confidence']}) — {v['reasoning']}"
            )
        return "\n".join(lines)
