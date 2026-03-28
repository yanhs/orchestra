"""Parallel mode — fan-out / fan-in with concurrent agents."""

import asyncio
from dataclasses import dataclass
from typing import Any

from ..agents.client import AgentClient, AgentResponse
from .base import BaseMode, OrchestraResult, UpdateCallback


@dataclass
class ParallelTask:
    """A subtask assigned to an agent."""

    agent: AgentClient
    description: str


class ParallelMode(BaseMode):
    """Fan-out / fan-in: agents work on subtasks concurrently, then a merge agent integrates results."""

    def __init__(
        self,
        tasks: list[ParallelTask],
        merge_agent: AgentClient | None = None,
        max_concurrent: int = 3,
        timeout_seconds: int = 600,
    ):
        self.tasks = tasks
        self.merge_agent = merge_agent
        self.max_concurrent = max_concurrent
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        topic: str,
        agents: list[AgentClient],  # unused, tasks carry agents
        on_update: UpdateCallback | None = None,
        **kwargs: Any,
    ) -> OrchestraResult:
        result = OrchestraResult(mode="parallel", topic=topic)

        # Run tasks concurrently with semaphore
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def run_task(task: ParallelTask) -> AgentResponse:
            async with semaphore:
                if on_update:
                    r = on_update(task.agent.display_name, "start", task.description)
                    if asyncio.iscoroutine(r):
                        await r

                prompt = (
                    f"## Main Goal\n{topic}\n\n"
                    f"## Your Subtask\n{task.description}\n\n"
                    "Focus only on your subtask. Be thorough and specific."
                )
                async def _stream(name, text):
                    if on_update:
                        r = on_update(name, "progress", text)
                        if asyncio.iscoroutine(r):
                            await r
                try:
                    response = await asyncio.wait_for(task.agent.run(prompt, on_stream=_stream), timeout=180)
                except asyncio.TimeoutError:
                    from ..agents.client import AgentResponse
                    response = AgentResponse(
                        agent_name=task.agent.display_name,
                        content="",
                        is_error=True,
                        error_message=f"Agent timed out after 180s",
                    )

                if on_update:
                    event = "error" if response.is_error else "done"
                    text = response.error_message if response.is_error else response.content
                    r = on_update(task.agent.display_name, event, text)
                    if asyncio.iscoroutine(r):
                        await r

                return response

        # Fan-out
        try:
            responses = await asyncio.wait_for(
                asyncio.gather(*[run_task(t) for t in self.tasks]),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            if on_update:
                r = on_update("Parallel", "error", f"Timeout after {self.timeout_seconds}s")
                if asyncio.iscoroutine(r):
                    await r
            return result

        for resp in responses:
            result.add_response(resp)

        # Fan-in: merge results
        if self.merge_agent and any(not r.is_error for r in responses):
            if on_update:
                r = on_update(self.merge_agent.display_name, "start", "Merging results")
                if asyncio.iscoroutine(r):
                    await r

            merge_prompt = self._build_merge_prompt(topic, responses)
            merge_response = await self.merge_agent.run(merge_prompt)

            if not merge_response.is_error:
                result.summary = merge_response.content
                result.add_response(merge_response)

            if on_update:
                r = on_update(self.merge_agent.display_name, "done", result.summary)
                if asyncio.iscoroutine(r):
                    await r

        return result

    def _build_merge_prompt(self, topic: str, responses: list[AgentResponse]) -> str:
        parts = [f"## Main Goal\n{topic}\n\n## Parallel Results\n"]

        for i, (task, resp) in enumerate(zip(self.tasks, responses), 1):
            if resp.is_error:
                parts.append(f"### {i}. {task.agent.display_name} — {task.description}\n*ERROR: {resp.error_message}*\n")
            else:
                parts.append(f"### {i}. {task.agent.display_name} — {task.description}\n{resp.content}\n")

        parts.append(
            "\n## Your Task\n"
            "Integrate these parallel results into a coherent whole. "
            "Identify any conflicts or gaps between the subtask outputs. "
            "Provide a unified summary and note any issues that need resolution."
        )

        return "\n".join(parts)
