"""Session persistence — maps agent roles to Claude session IDs."""

import json
from pathlib import Path

SESSIONS_FILE = Path(__file__).parent.parent.parent / "_orchestra" / "sessions.json"


def load_sessions() -> dict[str, str]:
    """Load session map from disk."""
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_sessions(sessions: dict[str, str]) -> None:
    """Save session map to disk."""
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))


def get_session(agent_name: str) -> str | None:
    """Get session ID for an agent."""
    return load_sessions().get(agent_name)


def set_session(agent_name: str, session_id: str) -> None:
    """Store session ID for an agent."""
    sessions = load_sessions()
    sessions[agent_name] = session_id
    save_sessions(sessions)
