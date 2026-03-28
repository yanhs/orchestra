"""OrchestraCoordinator — main orchestration logic."""

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
