"""FastAPI server for Agent Orchestra web UI."""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..agents.definition import load_config
from ..orchestrator.coordinator import OrchestraCoordinator

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "agents.yaml"
PUBLIC_PATH = Path(__file__).parent.parent.parent / "public"

app = FastAPI(title="Agent Orchestra")

# Serve static files
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

        # Stream callback — sends updates over WebSocket
        async def on_update(agent_name: str, event: str, text: str):
            await ws.send_json({
                "type": "update",
                "agent": agent_name,
                "event": event,
                "text": text,
            })

        # Run the selected mode
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

        # Send final result
        await ws.send_json({
            "type": "result",
            "summary": result.summary,
            "cost": result.total_cost,
            "duration_ms": result.total_duration_ms,
            "responses": len(result.responses),
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


def run_server(host: str = "0.0.0.0", port: int = 3015):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
