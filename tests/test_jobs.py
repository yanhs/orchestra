"""Tests for orchestrator/jobs.py — JobEvent, Job, JobManager."""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.orchestrator.jobs import Job, JobEvent, JobManager


# ---------------------------------------------------------------------------
# JobEvent
# ---------------------------------------------------------------------------

class TestJobEvent:
    def test_fields(self):
        ev = JobEvent(agent="Alice", event="start", text="Working")
        assert ev.agent == "Alice"
        assert ev.event == "start"
        assert ev.text == "Working"

    def test_auto_timestamp(self):
        before = time.time()
        ev = JobEvent(agent="X", event="done", text="")
        after = time.time()
        assert before <= ev.timestamp <= after

    def test_explicit_timestamp(self):
        ev = JobEvent(agent="X", event="done", text="", timestamp=12345.0)
        assert ev.timestamp == 12345.0

    def test_to_dict(self):
        ev = JobEvent(agent="Bob", event="error", text="Oops", timestamp=100.0)
        d = ev.to_dict()
        assert d == {"agent": "Bob", "event": "error", "text": "Oops", "ts": 100.0}


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class TestJob:
    def _make_job(self, **kwargs) -> Job:
        defaults = dict(id="test_job_001", goal="Do something")
        defaults.update(kwargs)
        return Job(**defaults)

    def test_default_status(self):
        job = self._make_job()
        assert job.status == "running"

    def test_auto_created_at(self):
        before = time.time()
        job = self._make_job()
        after = time.time()
        assert before <= job.created_at <= after

    def test_explicit_created_at(self):
        job = self._make_job(created_at=999.0)
        assert job.created_at == 999.0

    def test_add_event_appends(self):
        job = self._make_job()
        job.add_event("Alice", "start", "Hello")
        assert len(job.events) == 1
        assert job.events[0].agent == "Alice"

    def test_add_event_notifies_subscribers(self):
        job = self._make_job()
        q = job.subscribe()
        job.add_event("Alice", "done", "Result")
        assert not q.empty()
        ev = q.get_nowait()
        assert ev.agent == "Alice"

    def test_subscribe_returns_queue(self):
        job = self._make_job()
        q = job.subscribe()
        assert isinstance(q, asyncio.Queue)
        assert q in job._subscribers

    def test_unsubscribe_removes_queue(self):
        job = self._make_job()
        q = job.subscribe()
        assert q in job._subscribers
        job.unsubscribe(q)
        assert q not in job._subscribers

    def test_unsubscribe_unknown_queue_is_noop(self):
        job = self._make_job()
        q = asyncio.Queue()
        job.unsubscribe(q)  # should not raise

    def test_finish_sets_status(self):
        job = self._make_job()
        with patch.object(job, "_save"):
            job.finish("done", {"summary": "All good"})
        assert job.status == "done"
        assert job.result == {"summary": "All good"}
        assert job.finished_at > 0

    def test_finish_signals_subscribers(self):
        job = self._make_job()
        q = job.subscribe()
        with patch.object(job, "_save"):
            job.finish("done")
        # None sentinel is pushed to signal end
        assert q.get_nowait() is None

    def test_finish_saves_to_disk(self, tmp_path):
        with patch("src.orchestrator.jobs.LOG_DIR", tmp_path):
            job = self._make_job()
            job.finish("done", {"x": 1})
        saved = tmp_path / "test_job_001.json"
        assert saved.exists()
        data = json.loads(saved.read_text())
        assert data["id"] == "test_job_001"
        assert data["status"] == "done"
        assert data["goal"] == "Do something"

    def test_finish_serialises_events(self, tmp_path):
        with patch("src.orchestrator.jobs.LOG_DIR", tmp_path):
            job = self._make_job()
            job.add_event("Sys", "info", "hello")
            job.finish("done")
        data = json.loads((tmp_path / "test_job_001.json").read_text())
        assert len(data["events"]) == 1
        assert data["events"][0]["agent"] == "Sys"

    def test_to_summary(self):
        job = self._make_job(id="abc", goal="Goal", status="done", created_at=1.0, finished_at=2.0)
        job.add_event("A", "start", "x")
        s = job.to_summary()
        assert s["id"] == "abc"
        assert s["goal"] == "Goal"
        assert s["status"] == "done"
        assert s["events_count"] == 1

    def test_add_feedback_with_queue(self):
        job = self._make_job()
        job._feedback_queue = asyncio.Queue()
        job.add_feedback("Try again with more detail")
        assert job._feedback_queue.get_nowait() == "Try again with more detail"
        # Also recorded as an event
        assert any(e.event == "feedback" for e in job.events)

    def test_add_feedback_without_queue_does_not_raise(self):
        job = self._make_job()
        assert job._feedback_queue is None
        job.add_feedback("some text")  # should not raise
        assert any(e.event == "feedback" for e in job.events)


# ---------------------------------------------------------------------------
# JobManager
# ---------------------------------------------------------------------------

class TestJobManager:
    def _make_manager(self, tmp_path: Path) -> JobManager:
        with patch("src.orchestrator.jobs.LOG_DIR", tmp_path):
            mgr = JobManager()
        return mgr

    def test_create_returns_job(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        job = mgr.create("My goal")
        assert isinstance(job, Job)
        assert job.goal == "My goal"
        assert job.status == "running"

    def test_create_stores_job(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        job = mgr.create("goal")
        assert mgr.get(job.id) is job

    def test_get_missing_returns_none(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.get("nonexistent") is None

    def test_get_running_returns_most_recent(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        j1 = mgr.create("first")
        j1.created_at = 1000.0
        j2 = mgr.create("second")
        j2.created_at = 2000.0
        result = mgr.get_running()
        assert result is j2

    def test_get_running_none_when_all_finished(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        job = mgr.create("goal")
        with patch.object(job, "_save"):
            job.finish("done")
        assert mgr.get_running() is None

    def test_get_all_running(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        j1 = mgr.create("first")
        j2 = mgr.create("second")
        j3 = mgr.create("third")
        with patch.object(j3, "_save"):
            j3.finish("done")
        running = mgr.get_all_running()
        assert j1 in running
        assert j2 in running
        assert j3 not in running

    def test_list_all_returns_summaries(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr.create("a")
        mgr.create("b")
        result = mgr.list_all()
        assert len(result) == 2
        assert all(isinstance(r, dict) for r in result)

    def test_list_all_respects_limit(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        for i in range(5):
            mgr.create(f"goal {i}")
        result = mgr.list_all(limit=3)
        assert len(result) == 3

    def test_stop_cancels_task(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        job = mgr.create("goal")
        mock_task = MagicMock()
        mock_task.done.return_value = False
        job._task = mock_task
        with patch.object(job, "_save"):
            result = mgr.stop(job.id)
        assert result is True
        mock_task.cancel.assert_called_once()
        assert job.status == "stopped"

    def test_stop_cancels_child_tasks(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        job = mgr.create("goal")
        child1 = MagicMock()
        child1.done.return_value = False
        child2 = MagicMock()
        child2.done.return_value = True   # already done — should not be cancelled
        job._child_tasks = [child1, child2]
        job._task = MagicMock()
        with patch.object(job, "_save"):
            mgr.stop(job.id)
        child1.cancel.assert_called_once()
        child2.cancel.assert_not_called()
        assert job._child_tasks == []

    def test_stop_returns_false_for_nonexistent(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.stop("no_such_id") is False

    def test_stop_returns_false_for_finished_job(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        job = mgr.create("goal")
        with patch.object(job, "_save"):
            job.finish("done")
        assert mgr.stop(job.id) is False

    def test_load_from_disk_on_startup(self, tmp_path):
        """Jobs saved to disk should be loaded by a new JobManager instance."""
        # Write a fake job JSON
        job_data = {
            "id": "disk_job_001",
            "goal": "Persisted goal",
            "status": "done",
            "created_at": 1000.0,
            "finished_at": 1010.0,
            "events": [
                {"agent": "Sys", "event": "start", "text": "go", "ts": 1000.1}
            ],
            "result": {"summary": "done"},
        }
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "disk_job_001.json").write_text(json.dumps(job_data))

        with patch("src.orchestrator.jobs.LOG_DIR", tmp_path):
            mgr = JobManager()

        job = mgr.get("disk_job_001")
        assert job is not None
        assert job.goal == "Persisted goal"
        assert job.status == "done"
        assert len(job.events) == 1

    def test_load_from_disk_skips_invalid_json(self, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "bad.json").write_text("not json {{{{")
        with patch("src.orchestrator.jobs.LOG_DIR", tmp_path):
            mgr = JobManager()  # should not raise
        assert mgr.list_all() == []

    def test_load_from_disk_skips_non_json_files(self, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes.txt").write_text("ignore me")
        with patch("src.orchestrator.jobs.LOG_DIR", tmp_path):
            mgr = JobManager()
        assert mgr.list_all() == []
