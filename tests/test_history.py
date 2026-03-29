"""Tests for orchestrator/history.py — save_run, list_runs, get_run."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import src.orchestrator.history as history_module
from src.agents.client import AgentResponse
from src.modes.base import OrchestraResult
from src.orchestrator.history import get_run, list_runs, save_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    mode: str = "parallel",
    topic: str = "Test topic",
    summary: str = "All done",
) -> OrchestraResult:
    r = OrchestraResult(mode=mode, topic=topic, summary=summary)
    r.add_response(AgentResponse(agent_name="Alice", content="Alice output", cost=0.01, duration_ms=200))
    r.add_response(AgentResponse(agent_name="Bob", content="Bob output", cost=0.02, duration_ms=300))
    return r


# ---------------------------------------------------------------------------
# save_run
# ---------------------------------------------------------------------------

class TestSaveRun:
    def test_returns_path(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            p = save_run(_make_result())
        assert isinstance(p, Path)

    def test_creates_run_directory(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result())
        assert run_dir.is_dir()

    def test_creates_transcript_md(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result())
        assert (run_dir / "transcript.md").exists()

    def test_creates_result_json(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result())
        assert (run_dir / "result.json").exists()

    def test_transcript_contains_agent_names(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result())
        text = (run_dir / "transcript.md").read_text()
        assert "Alice" in text
        assert "Bob" in text

    def test_transcript_contains_content(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result())
        text = (run_dir / "transcript.md").read_text()
        assert "Alice output" in text
        assert "Bob output" in text

    def test_transcript_contains_summary(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result(summary="Great summary"))
        text = (run_dir / "transcript.md").read_text()
        assert "Great summary" in text

    def test_transcript_marks_error_agents(self, tmp_path):
        result = OrchestraResult(mode="parallel", topic="test")
        result.add_response(AgentResponse(
            agent_name="Broken", content="", is_error=True, error_message="Connection failed"
        ))
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(result)
        text = (run_dir / "transcript.md").read_text()
        assert "ERROR" in text
        assert "Connection failed" in text

    def test_result_json_fields(self, tmp_path):
        result = _make_result(mode="pipeline", topic="My topic", summary="Summary here")
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(result)
        meta = json.loads((run_dir / "result.json").read_text())
        assert meta["mode"] == "pipeline"
        assert meta["topic"] == "My topic"
        assert meta["summary"] == "Summary here"
        assert meta["responses"] == 2
        assert "Alice" in meta["agents"]
        assert "Bob" in meta["agents"]
        assert meta["cost"] == pytest.approx(0.03)
        assert "timestamp" in meta

    def test_run_dir_name_contains_mode(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result(mode="consensus"))
        assert "consensus" in run_dir.name

    def test_no_summary_section_when_empty(self, tmp_path):
        result = OrchestraResult(mode="parallel", topic="test", summary="")
        result.add_response(AgentResponse(agent_name="X", content="stuff"))
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(result)
        text = (run_dir / "transcript.md").read_text()
        assert "## Summary" not in text


# ---------------------------------------------------------------------------
# list_runs
# ---------------------------------------------------------------------------

class TestListRuns:
    def test_returns_empty_when_no_history_dir(self, tmp_path):
        missing = tmp_path / "no_runs"
        with patch.object(history_module, "HISTORY_DIR", missing):
            result = list_runs()
        assert result == []

    def test_returns_runs_in_reverse_order(self, tmp_path):
        # Patch datetime so successive calls return different timestamps
        from datetime import timezone
        import datetime as dt_module

        times = [
            dt_module.datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
            dt_module.datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
        ]
        call_count = [0]

        real_now = dt_module.datetime.now

        def fake_now(tz=None):
            idx = min(call_count[0], len(times) - 1)
            call_count[0] += 1
            return times[idx]

        with patch.object(history_module, "HISTORY_DIR", tmp_path), \
             patch("src.orchestrator.history.datetime") as mock_dt:
            mock_dt.now.side_effect = fake_now
            mock_dt.now.return_value = times[0]
            save_run(_make_result(topic="first"))
            save_run(_make_result(topic="second"))
            runs = list_runs()
        assert len(runs) == 2
        topics = {r["topic"] for r in runs}
        assert "first" in topics
        assert "second" in topics

    def test_respects_limit(self, tmp_path):
        # Create unique run dirs directly to avoid timestamp collision
        for i in range(5):
            run_dir = tmp_path / f"2026010{i}_000000_parallel"
            run_dir.mkdir()
            meta = {"mode": "parallel", "topic": f"run {i}", "summary": "",
                    "cost": 0.0, "duration_ms": 0, "responses": 0,
                    "agents": [], "timestamp": f"2026010{i}_000000"}
            import json
            (run_dir / "result.json").write_text(json.dumps(meta))

        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            runs = list_runs(limit=3)
        assert len(runs) == 3

    def test_each_run_has_id(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            save_run(_make_result())
            runs = list_runs()
        assert "id" in runs[0]

    def test_skips_invalid_json_dirs(self, tmp_path):
        bad_dir = tmp_path / "20260101_bad_parallel"
        bad_dir.mkdir()
        (bad_dir / "result.json").write_text("not json {{")
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            runs = list_runs()
        assert runs == []

    def test_skips_files_not_dirs(self, tmp_path):
        (tmp_path / "stray_file.txt").write_text("ignore")
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            runs = list_runs()
        assert runs == []


# ---------------------------------------------------------------------------
# get_run
# ---------------------------------------------------------------------------

class TestGetRun:
    def test_returns_none_for_missing_run(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            result = get_run("nonexistent_run_id")
        assert result is None

    def test_returns_metadata(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result(topic="Hello"))
            result = get_run(run_dir.name)
        assert result is not None
        assert result["topic"] == "Hello"

    def test_includes_transcript(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result())
            result = get_run(run_dir.name)
        assert "transcript" in result
        assert len(result["transcript"]) > 0

    def test_includes_id(self, tmp_path):
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            run_dir = save_run(_make_result())
            result = get_run(run_dir.name)
        assert result["id"] == run_dir.name

    def test_works_without_transcript_file(self, tmp_path):
        """If transcript.md is missing, result.json data is still returned."""
        run_dir = tmp_path / "20260101_test_parallel"
        run_dir.mkdir()
        meta = {"mode": "parallel", "topic": "t", "summary": "s"}
        (run_dir / "result.json").write_text(json.dumps(meta))
        with patch.object(history_module, "HISTORY_DIR", tmp_path):
            result = get_run("20260101_test_parallel")
        assert result["topic"] == "t"
        assert "transcript" not in result
