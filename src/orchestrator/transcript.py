"""Transcript builder for inter-agent message passing."""

from dataclasses import dataclass, field


@dataclass
class TranscriptEntry:
    """Single entry in the discussion transcript."""

    agent_name: str
    content: str
    round_num: int = 0


class Transcript:
    """Builds and formats a conversation transcript between agents."""

    def __init__(self) -> None:
        self.entries: list[TranscriptEntry] = []
        self._round = 1

    def add(self, agent_name: str, content: str) -> None:
        self.entries.append(
            TranscriptEntry(
                agent_name=agent_name,
                content=content,
                round_num=self._round,
            )
        )

    def next_round(self) -> None:
        self._round += 1

    def format(self, max_full_rounds: int = 2) -> str:
        """Format transcript. Keep last max_full_rounds in full, truncate earlier rounds."""
        if not self.entries:
            return ""
        max_round = max(e.round_num for e in self.entries)
        cutoff = max(1, max_round - max_full_rounds + 1)

        parts = []
        current_round = 0
        for entry in self.entries:
            if entry.round_num != current_round:
                current_round = entry.round_num
                if current_round > 1:
                    parts.append(f"\n--- Round {current_round} ---\n")

            if entry.round_num < cutoff:
                # Truncate early rounds to save context
                summary = entry.content[:300] + "..." if len(entry.content) > 300 else entry.content
                parts.append(f"**[{entry.agent_name}]** (summary): {summary}\n")
            else:
                parts.append(f"**[{entry.agent_name}]:**\n{entry.content}\n")
        return "\n".join(parts)
