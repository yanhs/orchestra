"""Background job manager — tasks survive browser disconnect."""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).parent.parent.parent / "_orchestra" / "jobs"


@dataclass
class JobEvent:
    """Single event in a job's stream."""
    agent: str
    event: str  # start, progress, done, error
    text: str
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).timestamp()

    def to_dict(self) -> dict:
        return {"agent": self.agent, "event": self.event, "text": self.text, "ts": self.timestamp}


@dataclass
class Job:
    """A background orchestration job."""
    id: str
    goal: str
    status: str = "running"  # running, done, error, stopped
    events: list[JobEvent] = field(default_factory=list)
    result: dict | None = None
    created_at: float = 0.0
    finished_at: float = 0.0
    _task: asyncio.Task | None = field(default=None, repr=False)
    _child_tasks: list[asyncio.Task] = field(default_factory=list, repr=False)
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)
    _feedback_queue: asyncio.Queue | None = field(default=None, repr=False)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).timestamp()

    def add_feedback(self, text: str):
        """Push user correction into the feedback queue."""
        if self._feedback_queue:
            self._feedback_queue.put_nowait(text)
        self.add_event("User", "feedback", text)

    def add_event(self, agent: str, event: str, text: str):
        ev = JobEvent(agent=agent, event=event, text=text)
        self.events.append(ev)
        # Notify all subscribers
        for q in self._subscribers:
            q.put_nowait(ev)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    def finish(self, status: str, result: dict | None = None):
        self.status = status
        self.result = result
        self.finished_at = datetime.now(timezone.utc).timestamp()
        # Signal end to subscribers
        for q in self._subscribers:
            q.put_nowait(None)
        self._save()

    def _save(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "events": [e.to_dict() for e in self.events],
            "result": self.result,
        }
        (LOG_DIR / f"{self.id}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "events_count": len(self.events),
        }


class JobManager:
    """Manages background orchestration jobs."""

    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._load_from_disk()

    def _load_from_disk(self):
        """Load finished jobs from disk on startup."""
        if not LOG_DIR.exists():
            return
        for f in sorted(LOG_DIR.iterdir(), key=lambda x: -x.stat().st_mtime)[:50]:
            if not f.suffix == '.json':
                continue
            try:
                data = json.loads(f.read_text())
                job_id = data["id"]
                if job_id in self.jobs:
                    continue
                job = Job(
                    id=job_id,
                    goal=data.get("goal", ""),
                    status=data.get("status", "done"),
                    created_at=data.get("created_at", 0),
                    finished_at=data.get("finished_at", 0),
                    result=data.get("result"),
                )
                # Restore events for replay
                for ev in data.get("events", []):
                    job.events.append(JobEvent(
                        agent=ev.get("agent", ""),
                        event=ev.get("event", ""),
                        text=ev.get("text", ""),
                        timestamp=ev.get("ts", 0),
                    ))
                self.jobs[job_id] = job
            except Exception:
                continue

    def create(self, goal: str) -> Job:
        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        job = Job(id=job_id, goal=goal)
        self.jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def get_running(self) -> Job | None:
        """Get the most recent running job, if any."""
        for job in sorted(self.jobs.values(), key=lambda j: -j.created_at):
            if job.status == "running":
                return job
        return None

    def get_all_running(self) -> list[Job]:
        """Get all currently running jobs."""
        return [j for j in self.jobs.values() if j.status == "running"]

    def list_all(self, limit: int = 20) -> list[dict]:
        jobs = sorted(self.jobs.values(), key=lambda j: -j.created_at)
        return [j.to_summary() for j in jobs[:limit]]

    def stop(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job and job.status == "running" and job._task:
            # Cancel all child tasks first (agent gather calls)
            for ct in job._child_tasks:
                if not ct.done():
                    ct.cancel()
            job._child_tasks.clear()
            # Then cancel the main supervisor task
            job._task.cancel()
            job.add_event("System", "error", "Stopped by user")
            job.finish("stopped")
            return True
        return False


# Global singleton
job_manager = JobManager()
