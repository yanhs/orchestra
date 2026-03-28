"""Run history — saves transcripts and results to disk."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..modes.base import OrchestraResult


HISTORY_DIR = Path(__file__).parent.parent.parent / "_orchestra" / "runs"


def save_run(result: OrchestraResult) -> Path:
    """Save a completed run to disk. Returns the run directory."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = HISTORY_DIR / f"{ts}_{result.mode}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Transcript as markdown
    transcript_lines = [f"# {result.mode.title()}: {result.topic}\n"]
    for resp in result.responses:
        if resp.is_error:
            transcript_lines.append(f"## {resp.agent_name} (ERROR)\n{resp.error_message}\n")
        else:
            transcript_lines.append(f"## {resp.agent_name}\n{resp.content}\n")
    if result.summary:
        transcript_lines.append(f"## Summary\n{result.summary}\n")

    (run_dir / "transcript.md").write_text("\n".join(transcript_lines))

    # Metadata as JSON
    meta = {
        "mode": result.mode,
        "topic": result.topic,
        "timestamp": ts,
        "cost": result.total_cost,
        "duration_ms": result.total_duration_ms,
        "responses": len(result.responses),
        "agents": [r.agent_name for r in result.responses],
        "summary": result.summary,
    }
    (run_dir / "result.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    return run_dir


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    """List recent runs from history."""
    if not HISTORY_DIR.exists():
        return []

    runs = []
    for run_dir in sorted(HISTORY_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        result_file = run_dir / "result.json"
        if result_file.exists():
            try:
                meta = json.loads(result_file.read_text())
                meta["id"] = run_dir.name
                runs.append(meta)
            except (json.JSONDecodeError, OSError):
                continue
        if len(runs) >= limit:
            break

    return runs


def get_run(run_id: str) -> dict[str, Any] | None:
    """Get a specific run by ID."""
    run_dir = HISTORY_DIR / run_id
    if not run_dir.is_dir():
        return None

    result = {}
    result_file = run_dir / "result.json"
    if result_file.exists():
        result = json.loads(result_file.read_text())

    transcript_file = run_dir / "transcript.md"
    if transcript_file.exists():
        result["transcript"] = transcript_file.read_text()

    result["id"] = run_id
    return result
