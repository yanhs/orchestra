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


LANDING_PATH = Path(__file__).parent.parent.parent / "landing"


# ── Pages ──

@app.get("/")
async def landing():
    return HTMLResponse(
        (LANDING_PATH / "index.html").read_text(),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/app")
@app.get("/app/")
async def dashboard():
    return HTMLResponse(
        (PUBLIC_PATH / "index.html").read_text(),
        headers={"Cache-Control": "no-store"},
    )


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
    prompt = f"""Generate a JSON config for an AI agent with the role: "{req.role_name}"

Return ONLY valid JSON (no markdown, no explanation) with these fields:
{{
  "id": "<lowercase_snake_case id>",
  "display_name": "<short display name>",
  "model": "<opus for complex analytical roles, sonnet for most roles, haiku for simple roles>",
  "max_turns": <number 20-50>,
  "allowed_tools": [<subset of: "Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch">],
  "system_prompt": "<2-5 bullet points describing the role>"
}}"""

    try:
        content = await _call_claude(prompt, model="haiku")
        return _parse_json(content)

    except Exception as e:
        return {"error": str(e)}


class AutoPlanRequest(BaseModel):
    topic: str


PLAN_PROMPT_TEMPLATE = """Analyze this task and propose exactly 3 plan variants — from FAST to THOROUGH.

TASK: "{topic}"

EXISTING AGENTS (reuse if suitable): {existing}

BASE MODES (can use as-is or combine into custom workflows):
- pipeline: Sequential handoff between agents
- discuss: All agents debate simultaneously in rounds
- parallel: Agents work on different subtasks at the same time
- consensus: Agents vote independently
- loop: Repeat a stage until quality criteria met (agent evaluates output, loops back if not good enough). In workflow: {{"type":"loop","agent":"evaluator_id","target_stage":0,"max_iterations":3,"criteria":"description of when to stop"}}

You can also design CUSTOM workflows by combining these in "options.workflow" — a sequence of stages:
  {{"workflow": [{{"type":"parallel","agents":["a","b"],"task":"research"}}, {{"type":"discuss","agents":["c","d"],"rounds":2}}, {{"type":"pipeline","steps":[{{"agent":"e","action":"write"}}]}}]}}

Return ONLY a valid JSON array of 3 plans:
[
  {{
    "label": "<creative short name for this approach>",
    "description": "<2-3 sentences: describe the workflow step by step, what each stage does>",
    "mode": "<pipeline|discuss|parallel|consensus|custom>",
    "reasoning": "<why this approach>",
    "agents": [
      {{
        "id": "<lowercase_snake_case>",
        "display_name": "<name>",
        "model": "<opus|sonnet|haiku>",
        "max_turns": <number>,
        "allowed_tools": [<subset of: "Read","Write","Edit","Bash","Glob","Grep","WebSearch","WebFetch">],
        "system_prompt": "<task-specific role instructions>"
      }}
    ],
    "options": {{"rounds": <number>}}
  }}
]

For "custom" mode, add "workflow" array in options describing stage-by-stage execution.

CRITICAL — MULTI-PHASE TASKS:
If the task is complex/ambitious (e.g. "заработай деньги", "build a startup", "create a product"), break it into PHASES.
Each phase is a separate workflow stage that depends on results of the previous phase.
Example for "заработай деньги":
  Phase 1: Brainstorm — parallel agents generate business ideas
  Phase 2: Evaluate — discuss and vote on best ideas
  Phase 3: Plan — pipeline to create detailed business plan for winner
  Phase 4: Execute — parallel agents implement different aspects
  Phase 5: Review — loop to check quality and iterate

Use "custom" mode with workflow stages. Each stage's agents get output from ALL previous stages as context.
Don't try to do everything in one simple pipeline — DECOMPOSE into logical phases.

VARIANT RULES:
- The 3 variants must differ significantly in depth and approach
- Variant 1 = fastest useful result. Maybe skip some phases, fewer agents per phase
- Variant 2 = solid middle ground. All key phases, moderate depth
- Variant 3 = maximum thoroughness. More phases, more agents, loops for quality, parallel exploration
- Do NOT use fixed numbers — adapt everything to the task
- Each variant MUST have its own interaction strategy. Describe step-by-step in "description"
- Choose models per agent based on role complexity

GENERAL RULES:
- For pipeline: add "steps" in options: [{{"agent":"id","action":"<verb>"}}]
- For parallel: add "tasks" in options: [{{"agent":"id","description":"subtask"}}]
- For loop: add in workflow: {{"type":"loop","agent":"id","target_stage":<N>,"max_iterations":3,"criteria":"..."}}
- Each agent's system_prompt must be specific to THIS task AND to their phase
- IMPORTANT: ALL text MUST be in the SAME LANGUAGE as the TASK"""


async def _call_claude(prompt: str, model: str = "opus") -> str:
    """Helper: call Claude and return text content."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, ResultMessage, TextBlock

    options = ClaudeAgentOptions(model=model, max_turns=1, permission_mode="plan")
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
    return content


def _parse_json(text: str):
    """Parse JSON from Claude response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


@app.post("/api/auto-plans")
async def auto_plans(req: AutoPlanRequest):
    """Generate 3 plan variants: fast, balanced, deep."""
    config = load_config(CONFIG_PATH)
    existing = {name: {"display_name": r.display_name, "model": r.model}
                for name, r in config.agents.items()}

    prompt = PLAN_PROMPT_TEMPLATE.format(topic=req.topic, existing=json.dumps(existing))

    try:
        content = await _call_claude(prompt, model="opus")
        plans = _parse_json(content)
        if not isinstance(plans, list):
            return {"error": "Expected array of plans"}
        return plans
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/auto-plan")
async def auto_plan(req: AutoPlanRequest):
    """Single plan (backward compat). Returns the balanced variant."""
    result = await auto_plans(req)
    if isinstance(result, dict) and result.get("error"):
        return result
    if isinstance(result, list) and len(result) >= 2:
        return result[1]  # balanced
    if isinstance(result, list) and len(result) >= 1:
        return result[0]
    return {"error": "No plans generated"}

    options = ClaudeAgentOptions(
        model="opus",
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

        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        return json.loads(text.strip())

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


DEFAULT_AGENTS_PATH = Path(__file__).parent.parent.parent / "config" / "agents.default.yaml"


@app.post("/api/agents/reset")
async def reset_agents():
    """Reset agents to defaults."""
    if DEFAULT_AGENTS_PATH.exists():
        shutil.copy2(DEFAULT_AGENTS_PATH, CONFIG_PATH)
    return {"ok": True}


# ── Saved Configs ──

ORCHESTRA_DIR = Path(__file__).parent.parent.parent / "_orchestra"
SESSIONS_FILE = ORCHESTRA_DIR / "sessions.json"
RUNS_DIR = ORCHESTRA_DIR / "runs"


@app.get("/api/configs")
async def list_configs():
    """List saved config presets."""
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    configs = []
    for d in sorted(CONFIGS_DIR.iterdir(), key=lambda x: -x.stat().st_mtime):
        if d.is_dir() and (d / "agents.yaml").exists():
            runs_dir = d / "runs"
            n_runs = len(list(runs_dir.iterdir())) if runs_dir.exists() else 0
            configs.append({"name": d.name, "modified": d.stat().st_mtime, "runs": n_runs})
        elif d.suffix == ".yaml":
            # Legacy single-file configs
            configs.append({"name": d.stem, "modified": d.stat().st_mtime, "runs": 0})
    return configs


@app.post("/api/configs/{name}")
async def save_config(name: str):
    """Save current config + all conversations as a named preset."""
    save_dir = CONFIGS_DIR / name
    save_dir.mkdir(parents=True, exist_ok=True)

    # Config
    shutil.copy2(CONFIG_PATH, save_dir / "agents.yaml")

    # Sessions
    if SESSIONS_FILE.exists():
        shutil.copy2(SESSIONS_FILE, save_dir / "sessions.json")

    # Runs (conversations)
    dest_runs = save_dir / "runs"
    if dest_runs.exists():
        shutil.rmtree(dest_runs)
    if RUNS_DIR.exists():
        shutil.copytree(RUNS_DIR, dest_runs)

    n_runs = len(list(dest_runs.iterdir())) if dest_runs.exists() else 0
    return {"ok": True, "name": name, "runs": n_runs}


@app.post("/api/configs/{name}/load")
async def load_saved_config(name: str):
    """Load a saved config preset + conversations."""
    save_dir = CONFIGS_DIR / name

    # Support legacy single-file configs
    if not save_dir.is_dir():
        legacy = CONFIGS_DIR / f"{name}.yaml"
        if legacy.exists():
            shutil.copy2(legacy, CONFIG_PATH)
            return {"ok": True, "runs": 0}
        return {"error": "Config not found"}

    # Config
    shutil.copy2(save_dir / "agents.yaml", CONFIG_PATH)

    # Sessions
    sess_src = save_dir / "sessions.json"
    if sess_src.exists():
        ORCHESTRA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sess_src, SESSIONS_FILE)

    # Runs
    runs_src = save_dir / "runs"
    if runs_src.exists():
        if RUNS_DIR.exists():
            shutil.rmtree(RUNS_DIR)
        shutil.copytree(runs_src, RUNS_DIR)
        n_runs = len(list(RUNS_DIR.iterdir()))
    else:
        n_runs = 0

    return {"ok": True, "runs": n_runs}


@app.delete("/api/configs/{name}")
async def delete_config(name: str):
    """Delete a saved config."""
    save_dir = CONFIGS_DIR / name
    if save_dir.is_dir():
        shutil.rmtree(save_dir)
        return {"ok": True}
    legacy = CONFIGS_DIR / f"{name}.yaml"
    if legacy.exists():
        legacy.unlink()
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
        elif mode == "custom":
            workflow = options.get("workflow", [])
            if not workflow:
                await ws.send_json({"type": "error", "text": "Custom mode requires workflow stages"})
                return
            result = await coordinator.custom(
                topic=topic,
                workflow=workflow,
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
        import traceback
        traceback.print_exc()
        active_agents.clear()
        try:
            await ws.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


def run_server(host: str = "0.0.0.0", port: int = 3025):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
