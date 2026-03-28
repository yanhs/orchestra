"""FastAPI server for Agent Orchestra web UI."""

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agents.definition import load_config
from ..orchestrator.coordinator import OrchestraCoordinator
from ..orchestrator.history import get_run, list_runs, save_run

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "agents.yaml"
CONFIGS_DIR = Path(__file__).parent.parent.parent / "config" / "saved"
PUBLIC_PATH = Path(__file__).parent.parent.parent / "public"

app = FastAPI(title="Agent Orchestra")

app.mount("/static", StaticFiles(directory=str(PUBLIC_PATH)), name="static")


# ── Helpers ──

def _read_yaml() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _write_yaml(data: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ── Pages ──

@app.get("/")
async def index():
    return HTMLResponse((PUBLIC_PATH / "index.html").read_text())


# ── Config API ──

@app.get("/api/config")
async def get_config():
    """Return full config: agents with all fields + modes."""
    config = load_config(CONFIG_PATH)
    return {
        "agents": {
            name: {
                "display_name": role.display_name,
                "model": role.model,
                "system_prompt": role.system_prompt,
                "allowed_tools": role.allowed_tools,
                "max_turns": role.max_turns,
            }
            for name, role in config.agents.items()
        },
        "modes": list(config.modes.keys()),
    }


# ── Agent CRUD ──

class AgentData(BaseModel):
    display_name: str
    model: str = "sonnet"
    system_prompt: str = ""
    allowed_tools: list[str] = []
    max_turns: int = 50


@app.put("/api/agents/{name}")
async def upsert_agent(name: str, data: AgentData):
    """Create or update an agent."""
    raw = _read_yaml()
    if "agents" not in raw:
        raw["agents"] = {}
    raw["agents"][name] = {
        "display_name": data.display_name,
        "model": data.model,
        "system_prompt": data.system_prompt,
        "allowed_tools": data.allowed_tools,
        "max_turns": data.max_turns,
    }
    _write_yaml(raw)
    return {"ok": True, "name": name}


class GenerateRequest(BaseModel):
    role_name: str


@app.post("/api/agents/generate")
async def generate_agent(req: GenerateRequest):
    """Use Claude to auto-generate agent config from a role name."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, ResultMessage, TextBlock

    prompt = f"""Generate a JSON config for an AI agent with the role: "{req.role_name}"

Return ONLY valid JSON (no markdown, no explanation) with these fields:
{{
  "id": "<lowercase_snake_case id>",
  "display_name": "<short display name>",
  "model": "<opus for complex analytical roles, sonnet for most roles, haiku for simple roles>",
  "max_turns": <number 20-50>,
  "allowed_tools": [<subset of: "Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch">],
  "system_prompt": "<2-5 bullet points describing the role, what it does, how it should behave. Start with 'You are a...'>"
}}

Choose tools that match the role. Read-only roles get Read/Glob/Grep. Coding roles get Write/Edit/Bash too. Research roles get WebSearch/WebFetch."""

    options = ClaudeAgentOptions(
        model="haiku",
        max_turns=1,
        permission_mode="plan",
    )

    try:
        client = ClaudeSDKClient(options)
        content = ""
        try:
            await client.connect()
            await client.query(prompt)
            async for msg in client.receive_messages():
                if isinstance(msg, ResultMessage):
                    if msg.result:
                        content = msg.result
                    break
                elif isinstance(msg, AssistantMessage):
                    for block in msg.content or []:
                        if isinstance(block, TextBlock):
                            content += block.text
        finally:
            await client.disconnect()

        # Parse JSON from response (handle markdown code blocks)
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        result = json.loads(text.strip())
        return result

    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/agents/{name}")
async def delete_agent(name: str):
    """Delete an agent."""
    raw = _read_yaml()
    if name in raw.get("agents", {}):
        del raw["agents"][name]
        _write_yaml(raw)
        return {"ok": True}
    return {"error": "Agent not found"}


# ── Saved Configs ──

@app.get("/api/configs")
async def list_configs():
    """List saved config presets."""
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    return [
        {"name": f.stem, "modified": f.stat().st_mtime}
        for f in sorted(CONFIGS_DIR.glob("*.yaml"), key=lambda f: -f.stat().st_mtime)
    ]


@app.post("/api/configs/{name}")
async def save_config(name: str):
    """Save current config as a named preset."""
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG_PATH, CONFIGS_DIR / f"{name}.yaml")
    return {"ok": True, "name": name}


@app.post("/api/configs/{name}/load")
async def load_saved_config(name: str):
    """Load a saved config preset."""
    src = CONFIGS_DIR / f"{name}.yaml"
    if not src.exists():
        return {"error": "Config not found"}
    shutil.copy2(src, CONFIG_PATH)
    return {"ok": True}


@app.delete("/api/configs/{name}")
async def delete_config(name: str):
    """Delete a saved config."""
    src = CONFIGS_DIR / f"{name}.yaml"
    if src.exists():
        src.unlink()
        return {"ok": True}
    return {"error": "Config not found"}


# ── History ──

@app.get("/api/history")
async def api_history(limit: int = 30):
    return list_runs(limit=limit)


@app.get("/api/history/{run_id}")
async def api_run(run_id: str):
    run = get_run(run_id)
    if not run:
        return {"error": "Run not found"}
    return run


# ── WebSocket Run ──

# Track live agent activity for the diagram
active_agents: dict[str, str] = {}  # agent_name -> status ("working"/"idle")


@app.get("/api/activity")
async def get_activity():
    """Current agent activity status for the diagram."""
    return active_agents


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
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
            # Update activity tracking
            if event == "start":
                active_agents[agent_name] = "working"
            elif event in ("done", "error"):
                active_agents[agent_name] = "idle"

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

        # Clear activity
        active_agents.clear()

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
        active_agents.clear()
    except Exception as e:
        active_agents.clear()
        try:
            await ws.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


def run_server(host: str = "0.0.0.0", port: int = 3025):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
