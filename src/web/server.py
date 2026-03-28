"""FastAPI server for Agent Orchestra web UI."""

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..agents.definition import load_config
from ..orchestrator.coordinator import OrchestraCoordinator
from ..orchestrator.history import get_run, list_runs, save_run

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "agents.yaml"
PUBLIC_PATH = Path(__file__).parent.parent.parent / "public"

app = FastAPI(title="Agent Orchestra")

app.mount("/static", StaticFiles(directory=str(PUBLIC_PATH)), name="static")


@app.get("/")
async def index():
    return HTMLResponse((PUBLIC_PATH / "index.html").read_text())


@app.get("/api/config")
async def get_config():
    """Return available agents and modes."""
    config = load_config(CONFIG_PATH)
    return {
        "agents": {
            name: {
                "display_name": role.display_name,
                "model": role.model,
            }
            for name, role in config.agents.items()
        },
        "modes": list(config.modes.keys()),
    }


@app.get("/api/history")
async def api_history(limit: int = 30):
    """List recent runs."""
    return list_runs(limit=limit)


@app.get("/api/history/{run_id}")
async def api_run(run_id: str):
    """Get a specific run with transcript."""
    run = get_run(run_id)
    if not run:
        return {"error": "Run not found"}
    return run


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    """WebSocket endpoint for running orchestration.

    Client sends: {mode, topic, agents, options}
    Server streams: {type, agent, event, text} messages
    """
    await ws.accept()

    try:
        msg = await ws.receive_json()
        mode = msg.get("mode", "discuss")
        topic = msg.get("topic", "")
        agent_names = msg.get("agents", [])
        options = msg.get("options", {})
        project_path = msg.get("project_path")

        if not topic:
            await ws.send_json({"type": "error", "text": "No topic provided"})
            return

        config = load_config(CONFIG_PATH)
        coordinator = OrchestraCoordinator(
            config=config,
            project_path=Path(project_path) if project_path else None,
        )

        async def on_update(agent_name: str, event: str, text: str):
            await ws.send_json({
                "type": "update",
                "agent": agent_name,
                "event": event,
                "text": text,
            })

        if mode == "discuss":
            result = await coordinator.discuss(
                topic=topic,
                agent_names=agent_names or None,
                rounds=options.get("rounds"),
                on_update=on_update,
            )
        elif mode == "pipeline":
            steps = options.get("steps")
            parsed_steps = None
            if steps:
                parsed_steps = [(s["agent"], s["action"]) for s in steps]
            result = await coordinator.pipeline(
                topic=topic,
                steps=parsed_steps,
                on_update=on_update,
            )
        elif mode == "parallel":
            tasks = options.get("tasks", [])
            parsed_tasks = [(t["agent"], t["description"]) for t in tasks]
            result = await coordinator.parallel(
                topic=topic,
                tasks=parsed_tasks,
                on_update=on_update,
            )
        elif mode == "consensus":
            result = await coordinator.consensus(
                topic=topic,
                agent_names=agent_names or None,
                on_update=on_update,
            )
        else:
            await ws.send_json({"type": "error", "text": f"Unknown mode: {mode}"})
            return

        # Save to history
        run_dir = save_run(result)

        await ws.send_json({
            "type": "result",
            "summary": result.summary,
            "cost": result.total_cost,
            "duration_ms": result.total_duration_ms,
            "responses": len(result.responses),
            "run_id": run_dir.name,
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


def run_server(host: str = "0.0.0.0", port: int = 3025):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
