"""Pipeline mode — sequential handoff between agents."""

import asyncio
from dataclasses import dataclass
from typing import Any

from ..agents.client import AgentClient
from ..orchestrator.transcript import Transcript
from .base import BaseMode, OrchestraResult, UpdateCallback


@dataclass
class PipelineStep:
    """A single step in the pipeline."""

    agent: AgentClient
    action: str  # e.g. "design", "implement", "review", "test"


class PipelineMode(BaseMode):
    """Sequential pipeline: each agent receives the previous agent's output.

    Optionally loops back for rework when a reviewer flags critical issues.
    """

    def __init__(
        self,
        steps: list[PipelineStep],
        allow_rework: bool = True,
        max_rework_cycles: int = 1,
    ):
        self.steps = steps
        self.allow_rework = allow_rework
        self.max_rework_cycles = max_rework_cycles

    async def execute(
        self,
        topic: str,
        agents: list[AgentClient],  # unused, steps carry agents
        on_update: UpdateCallback | None = None,
        **kwargs: Any,
    ) -> OrchestraResult:
        result = OrchestraResult(mode="pipeline", topic=topic)
        transcript = Transcript()
        rework_count = 0

        step_num = 0
        while step_num < len(self.steps):
            step = self.steps[step_num]
            agent = step.agent
            step_label = f"Step {step_num + 1}/{len(self.steps)}: {step.action}"

            if on_update:
                r = on_update(agent.display_name, "start", step_label)
                if asyncio.iscoroutine(r):
                    await r

            prompt = self._build_prompt(topic, transcript, step, step_num)

            async def _stream(name, text):
                if on_update:
                    r = on_update(name, "progress", text)
                    if asyncio.iscoroutine(r):
                        await r

            response = await agent.run(prompt, on_stream=_stream)

            if response.is_error:
                if on_update:
                    r = on_update(agent.display_name, "error", response.error_message)
                    if asyncio.iscoroutine(r):
                        await r
                step_num += 1
                continue

            transcript.add(f"{agent.display_name} ({step.action})", response.content)
            result.add_response(response)

            if on_update:
                r = on_update(agent.display_name, "done", response.content)
                if asyncio.iscoroutine(r):
                    await r

            # Check for rework: if a review step flags critical issues
            if (
                self.allow_rework
                and step.action == "review"
                and rework_count < self.max_rework_cycles
                and self._needs_rework(response.content)
            ):
                rework_count += 1
                # Find the implementation step to redo
                impl_step = self._find_step("implement")
                if impl_step is not None:
                    if on_update:
                        r = on_update(
                            "Pipeline",
                            "start",
                            f"Rework cycle {rework_count}: sending back to {self.steps[impl_step].agent.display_name}",
                        )
                        if asyncio.iscoroutine(r):
                            await r
                    step_num = impl_step
                    continue

            step_num += 1

        return result

    def _build_prompt(
        self,
        topic: str,
        transcript: Transcript,
        step: PipelineStep,
        step_num: int,
    ) -> str:
        parts = [f"## Task\n{topic}"]

        if transcript.entries:
            parts.append(f"## Previous Steps\n{transcript.format()}")

        action_instructions = {
            "design": (
                "Create a design for this task. Include:\n"
                "- Architecture overview\n"
                "- Key components and their responsibilities\n"
                "- Important design decisions\n"
                "- File structure if applicable"
            ),
            "implement": (
                "Implement this based on the design above. "
                "Write clean, working code. Follow existing project patterns."
            ),
            "review": (
                "Review the implementation above. Check for:\n"
                "- Bugs and logic errors\n"
                "- Security issues\n"
                "- Performance problems\n"
                "- Code style and best practices\n\n"
                "Rate each issue as: CRITICAL / MAJOR / MINOR / NIT\n"
                "If there are CRITICAL issues, start your response with 'CRITICAL:'"
            ),
            "test": (
                "Write tests for the implementation above. Include:\n"
                "- Unit tests for key functions\n"
                "- Edge cases\n"
                "- Integration test suggestions"
            ),
        }

        instruction = action_instructions.get(
            step.action,
            f"Perform the '{step.action}' step for this task. "
            "Use the results from previous steps above as input. "
            "Be thorough and produce a clear, structured output for the next step.",
        )
        parts.append(f"## Your Task: {step.action.title()}\n{instruction}")

        return "\n\n".join(parts)

    def _needs_rework(self, review_content: str) -> bool:
        """Check if review flagged critical issues requiring rework."""
        content_lower = review_content.lower()
        return content_lower.startswith("critical:") or "critical:" in content_lower[:200]

    def _find_step(self, action: str) -> int | None:
        """Find the index of a step by action name."""
        for i, step in enumerate(self.steps):
            if step.action == action:
                return i
        return None
