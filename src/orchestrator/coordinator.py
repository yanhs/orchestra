"""OrchestraCoordinator — main orchestration logic."""

from pathlib import Path

from ..agents.client import AgentClient
from ..agents.definition import OrchestraConfig, load_config
from ..modes.base import OrchestraResult, UpdateCallback
from ..modes.discussion import DiscussionMode

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
        """Run a discussion between agents.

        Args:
            topic: The topic/question to discuss.
            agent_names: Which agents participate. Defaults to mode config.
            rounds: Number of discussion rounds. Defaults to mode config.
            on_update: Callback for progress updates.
        """
        mode_config = self.config.get_mode("discussion")

        names = agent_names or mode_config.default_agents
        if not names:
            names = ["architect", "developer", "reviewer"]

        agents = [self._make_agent(n) for n in names]

        max_rounds = rounds or mode_config.max_rounds

        # Summarizer
        summarizer = None
        summarizer_name = mode_config.summarizer
        if summarizer_name and summarizer_name in self.config.agents:
            summarizer = self._make_agent(summarizer_name)

        mode = DiscussionMode(
            max_rounds=max_rounds,
            summarizer=summarizer,
        )

        return await mode.execute(topic, agents, on_update=on_update)
