"""OrchestraCoordinator — main orchestration logic."""

import asyncio
from pathlib import Path

from ..agents.client import AgentClient
from ..agents.definition import OrchestraConfig, load_config
from ..modes.base import OrchestraResult, UpdateCallback
from ..modes.consensus import ConsensusMode
from ..modes.discussion import DiscussionMode
from ..modes.parallel import ParallelMode, ParallelTask
from ..modes.pipeline import PipelineMode, PipelineStep

# Default config location relative to package
DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config" / "agents.yaml"


class OrchestraCoordinator:
    """Coordinates agent interactions across different modes."""

    def __init__(
        self,
        config: OrchestraConfig | None = None,
        config_path: Path | None = None,
        project_path: Path | None = None,
        cli_path: str | None = None,
    ):
        if config:
            self.config = config
        else:
            path = config_path or DEFAULT_CONFIG
            self.config = load_config(path)

        self.project_path = project_path or Path.cwd()
        self.cli_path = cli_path

    def _make_agent(self, name: str) -> AgentClient:
        """Create an AgentClient for a given role name."""
        role = self.config.get_agent(name)
        return AgentClient(
            role=role,
            project_path=self.project_path,
            cli_path=self.cli_path,
        )

    async def discuss(
        self,
        topic: str,
        agent_names: list[str] | None = None,
        rounds: int | None = None,
        on_update: UpdateCallback | None = None,
    ) -> OrchestraResult:
        """Run a round-robin discussion between agents."""
        mode_config = self.config.get_mode("discussion")

        names = agent_names or mode_config.default_agents
        if not names:
            names = ["architect", "developer", "reviewer"]

        agents = [self._make_agent(n) for n in names]
        max_rounds = rounds or mode_config.max_rounds

        # Find a summarizer: from config, or from available agents, or create ad-hoc
        summarizer = None
        summarizer_name = mode_config.summarizer
        if summarizer_name and summarizer_name in self.config.agents:
            summarizer = self._make_agent(summarizer_name)
        else:
            # Use any agent not in the discussion as summarizer
            for aname in self.config.agents:
                if aname not in names:
                    summarizer = self._make_agent(aname)
                    break
            if not summarizer:
                # Create ad-hoc summarizer from first agent
                from ..agents.client import AgentClient
                from ..agents.definition import AgentRole
                summarizer = AgentClient(
                    role=AgentRole(
                        name="_summarizer",
                        display_name="Summarizer",
                        model="sonnet",
                        system_prompt="You summarize discussions. Structure: 1) Key decisions 2) Open questions 3) Action items. Be concise. Always respond in the same language as the discussion topic.",
                        allowed_tools=[],
                        max_turns=10,
                    ),
                    project_path=self.project_path,
                    cli_path=self.cli_path,
                )

        mode = DiscussionMode(max_rounds=max_rounds, summarizer=summarizer)
        return await mode.execute(topic, agents, on_update=on_update)

    async def pipeline(
        self,
        topic: str,
        steps: list[tuple[str, str]] | None = None,
        on_update: UpdateCallback | None = None,
    ) -> OrchestraResult:
        """Run a sequential pipeline: each agent hands off to the next.

        Args:
            topic: The task to process through the pipeline.
            steps: List of (agent_name, action) tuples.
                   e.g. [("architect", "design"), ("developer", "implement")]
                   Defaults to mode config.
        """
        mode_config = self.config.get_mode("pipeline")

        if steps:
            pipeline_steps = [
                PipelineStep(agent=self._make_agent(name), action=action)
                for name, action in steps
            ]
        else:
            default_steps = mode_config.settings.get("default_steps", [])
            pipeline_steps = [
                PipelineStep(
                    agent=self._make_agent(s["agent"]),
                    action=s["action"],
                )
                for s in default_steps
            ]

        if not pipeline_steps:
            pipeline_steps = [
                PipelineStep(self._make_agent("architect"), "design"),
                PipelineStep(self._make_agent("developer"), "implement"),
                PipelineStep(self._make_agent("reviewer"), "review"),
            ]

        mode = PipelineMode(
            steps=pipeline_steps,
            allow_rework=mode_config.settings.get("allow_rework", True),
            max_rework_cycles=mode_config.settings.get("max_rework_cycles", 1),
        )
        return await mode.execute(topic, [], on_update=on_update)

    async def parallel(
        self,
        topic: str,
        tasks: list[tuple[str, str]],
        on_update: UpdateCallback | None = None,
    ) -> OrchestraResult:
        """Run agents in parallel on different subtasks, then merge.

        Args:
            topic: The overall goal.
            tasks: List of (agent_name, subtask_description) tuples.
        """
        mode_config = self.config.get_mode("parallel")

        parallel_tasks = [
            ParallelTask(agent=self._make_agent(name), description=desc)
            for name, desc in tasks
        ]

        merge_name = mode_config.settings.get("merge_agent")
        merge_agent = self._make_agent(merge_name) if merge_name and merge_name in self.config.agents else None

        mode = ParallelMode(
            tasks=parallel_tasks,
            merge_agent=merge_agent,
            max_concurrent=mode_config.settings.get("max_concurrent", 3),
            timeout_seconds=mode_config.settings.get("timeout_seconds", 600),
        )
        return await mode.execute(topic, [], on_update=on_update)

    async def consensus(
        self,
        topic: str,
        agent_names: list[str] | None = None,
        on_update: UpdateCallback | None = None,
    ) -> OrchestraResult:
        """Agents vote independently on a question. Supermajority decides.

        Args:
            topic: The decision question.
            agent_names: Which agents vote. Defaults to mode config.
        """
        mode_config = self.config.get_mode("consensus")

        names = agent_names or mode_config.settings.get("default_agents", [])
        if not names:
            names = ["architect", "developer", "reviewer"]

        agents = [self._make_agent(n) for n in names]

        mode = ConsensusMode(
            threshold=mode_config.settings.get("threshold", 0.67),
            max_rounds=mode_config.settings.get("max_rounds", 3),
        )
        return await mode.execute(topic, agents, on_update=on_update)

    async def custom(
        self,
        topic: str,
        workflow: list[dict],
        on_update: UpdateCallback | None = None,
    ) -> OrchestraResult:
        """Execute a custom multi-stage workflow.

        Each stage is a dict with:
            type: "pipeline" | "discuss" | "parallel" | "consensus"
            agents: list of agent IDs
            + mode-specific fields (steps, tasks, rounds, task)
        """
        result = OrchestraResult(mode="custom", topic=topic)
        transcript_so_far = ""

        for i, stage in enumerate(workflow):
            stage_type = stage.get("type", "discuss")
            agent_ids = stage.get("agents", [])
            stage_topic = topic
            if transcript_so_far:
                stage_topic = f"{topic}\n\n## Previous stages output:\n{transcript_so_far}"

            if on_update:
                r = on_update("Workflow", "start", f"Stage {i+1}/{len(workflow)}: {stage_type}")
                if asyncio.iscoroutine(r):
                    await r

            if stage_type == "pipeline":
                steps = stage.get("steps", [{"agent": a, "action": "process"} for a in agent_ids])
                stage_result = await self.pipeline(
                    topic=stage_topic,
                    steps=[(s["agent"], s["action"]) for s in steps],
                    on_update=on_update,
                )
            elif stage_type == "discuss":
                stage_result = await self.discuss(
                    topic=stage_topic,
                    agent_names=agent_ids,
                    rounds=stage.get("rounds", 2),
                    on_update=on_update,
                )
            elif stage_type == "parallel":
                tasks = stage.get("tasks", [{"agent": a, "description": stage.get("task", "process")} for a in agent_ids])
                stage_result = await self.parallel(
                    topic=stage_topic,
                    tasks=[(t["agent"], t["description"]) for t in tasks],
                    on_update=on_update,
                )
            elif stage_type == "consensus":
                stage_result = await self.consensus(
                    topic=stage_topic,
                    agent_names=agent_ids,
                    on_update=on_update,
                )
            elif stage_type == "loop":
                # Loop: evaluator checks output, reruns target stage if needed
                evaluator_id = stage.get("agent", agent_ids[0] if agent_ids else None)
                target_idx = stage.get("target_stage", max(0, i - 1))
                max_iter = stage.get("max_iterations", 3)
                criteria = stage.get("criteria", "quality is sufficient")

                for iteration in range(max_iter):
                    if on_update:
                        r = on_update("Loop", "start", f"Iteration {iteration+1}/{max_iter}: evaluating...")
                        if asyncio.iscoroutine(r):
                            await r

                    # Evaluator checks current output
                    eval_prompt = (
                        f"{stage_topic}\n\n"
                        f"## Current output to evaluate:\n{transcript_so_far}\n\n"
                        f"## Criteria: {criteria}\n\n"
                        "Reply with EXACTLY one line:\n"
                        "PASS: <reason> — if the output meets the criteria\n"
                        "FAIL: <what needs improvement> — if it does not"
                    )
                    if evaluator_id:
                        evaluator = self._make_agent(evaluator_id)
                        eval_response = await evaluator.run(eval_prompt)
                        result.add_response(eval_response)

                        if on_update:
                            r = on_update(evaluator.display_name, "done", eval_response.content)
                            if asyncio.iscoroutine(r):
                                await r

                        if eval_response.content.strip().upper().startswith("PASS"):
                            break

                        # Re-run target stage
                        if target_idx < len(workflow) and target_idx < i:
                            target = workflow[target_idx]
                            t_type = target.get("type", "discuss")
                            t_agents = target.get("agents", [])
                            rework_topic = f"{stage_topic}\n\n## Feedback: {eval_response.content}\n\nPlease improve based on the feedback above."

                            if on_update:
                                r = on_update("Loop", "start", f"Reworking stage {target_idx+1} ({t_type})")
                                if asyncio.iscoroutine(r):
                                    await r

                            # Execute target stage again with feedback
                            if t_type == "pipeline":
                                steps = target.get("steps", [{"agent": a, "action": "improve"} for a in t_agents])
                                rework_result = await self.pipeline(topic=rework_topic, steps=[(s["agent"], s["action"]) for s in steps], on_update=on_update)
                            elif t_type == "discuss":
                                rework_result = await self.discuss(topic=rework_topic, agent_names=t_agents, rounds=target.get("rounds", 1), on_update=on_update)
                            elif t_type == "parallel":
                                tasks = target.get("tasks", [{"agent": a, "description": "improve"} for a in t_agents])
                                rework_result = await self.parallel(topic=rework_topic, tasks=[(t["agent"], t["description"]) for t in tasks], on_update=on_update)
                            else:
                                break

                            for resp in rework_result.responses:
                                result.add_response(resp)
                            rework_text = rework_result.summary or "\n".join(r.content for r in rework_result.responses if not r.is_error)
                            transcript_so_far += f"\n### Loop iteration {iteration+1} rework:\n{rework_text}\n"

                stage_result = None  # loop doesn't produce its own result
            else:
                continue

            # Accumulate results
            if stage_result:
                for resp in stage_result.responses:
                    result.add_response(resp)
                stage_text = stage_result.summary or "\n".join(
                    r.content for r in stage_result.responses if not r.is_error
                )
                transcript_so_far += f"\n### Stage {i+1} ({stage_type}):\n{stage_text}\n"

        result.summary = transcript_so_far
        return result
