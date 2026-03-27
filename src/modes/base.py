"""Base mode and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from ..agents.client import AgentClient, AgentResponse


@dataclass
class OrchestraResult:
    """Result of an orchestration run."""

    mode: str
    topic: str
    responses: list[AgentResponse] = field(default_factory=list)
    summary: str = ""
    total_cost: float = 0.0
    total_duration_ms: int = 0

    def add_response(self, response: AgentResponse) -> None:
        self.responses.append(response)
        self.total_cost += response.cost
        self.total_duration_ms += response.duration_ms


# Callback: async fn(agent_name, event_type, text)
UpdateCallback = Callable[[str, str, str], Any]


class BaseMode(ABC):
    """Abstract base for interaction modes."""

    @abstractmethod
    async def execute(
        self,
        topic: str,
        agents: list[AgentClient],
        on_update: UpdateCallback | None = None,
        **kwargs: Any,
    ) -> OrchestraResult:
        ...
