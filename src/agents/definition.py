"""Agent role definitions and YAML loader."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AgentRole:
    """Definition of an agent role."""

    name: str
    display_name: str
    model: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    max_turns: int = 50


@dataclass
class ModeConfig:
    """Configuration for an interaction mode."""

    name: str
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def max_rounds(self) -> int:
        return self.settings.get("max_rounds", 2)

    @property
    def default_agents(self) -> list[str]:
        return self.settings.get("default_agents", [])

    @property
    def summarizer(self) -> str | None:
        return self.settings.get("summarizer")


@dataclass
class OrchestraConfig:
    """Full orchestra configuration."""

    agents: dict[str, AgentRole]
    modes: dict[str, ModeConfig]

    def get_agent(self, name: str) -> AgentRole:
        if name not in self.agents:
            available = ", ".join(self.agents.keys())
            raise ValueError(f"Unknown agent '{name}'. Available: {available}")
        return self.agents[name]

    def get_mode(self, name: str) -> ModeConfig:
        if name not in self.modes:
            available = ", ".join(self.modes.keys())
            raise ValueError(f"Unknown mode '{name}'. Available: {available}")
        return self.modes[name]


def load_config(config_path: Path) -> OrchestraConfig:
    """Load orchestra configuration from YAML file."""
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    agents = {}
    for name, data in raw.get("agents", {}).items():
        agents[name] = AgentRole(
            name=name,
            display_name=data.get("display_name", name.title()),
            model=data.get("model", "sonnet"),
            system_prompt=data.get("system_prompt", ""),
            allowed_tools=data.get("allowed_tools", []),
            max_turns=data.get("max_turns", 50),
        )

    modes = {}
    for name, data in raw.get("modes", {}).items():
        modes[name] = ModeConfig(name=name, settings=data or {})

    return OrchestraConfig(agents=agents, modes=modes)
