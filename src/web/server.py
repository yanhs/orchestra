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


class SelfRepairRequest(BaseModel):
    error: str
    context: str = ""


ORCHESTRA_PROJECT_PATH = Path(__file__).parent.parent.parent


@app.post("/api/self-repair")
async def self_repair(req: SelfRepairRequest):
    """Launch a Claude agent to diagnose and fix errors in the orchestra code."""
    prompt = f"""You are a senior developer fixing a bug in the Agent Orchestra system.
The system is located at: {ORCHESTRA_PROJECT_PATH}

ERROR: {req.error}

CONTEXT: {req.context}

Key files:
- src/web/server.py — FastAPI backend, API endpoints, auto-plan logic
- src/orchestrator/coordinator.py — mode execution (discuss, pipeline, parallel, consensus, custom)
- src/modes/discussion.py, pipeline.py, parallel.py, consensus.py — mode implementations
- src/agents/client.py — ClaudeSDKClient wrapper
- public/index.html — frontend SPA

Diagnose the issue, fix it, and verify your fix. After fixing, the service needs restart:
  Run: systemctl --user restart orchestra-web

Be precise. Make minimal changes to fix the specific error."""

    try:
        content = await _call_claude(prompt, model="opus")
        # After repair, restart the service
        import subprocess
        subprocess.Popen(
            ["systemctl", "--user", "restart", "orchestra-web"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "diagnosis": content[:500]}
    except Exception as e:
        return {"error": str(e)}


ANALYZE_PROMPT = """You are a task analyst. Analyze the user's request and produce a structured understanding.

USER REQUEST: "{topic}"

Return ONLY valid JSON:
{{
  "understood_task": "<restate what the user actually wants in 2-3 clear sentences>",
  "phases": ["<phase 1 name>", "<phase 2 name>", ...],
  "phase_descriptions": ["<what phase 1 should accomplish>", "<what phase 2 should accomplish>", ...],
  "complexity": "<simple|moderate|complex|ambitious>",
  "key_challenges": ["<challenge 1>", "<challenge 2>", ...],
  "success_criteria": "<what does a good result look like>"
}}

Rules:
- Decompose ANY task into logical phases (even simple ones have at least 1-2 phases)
- Be specific about what each phase produces
- ALL text MUST be in the SAME LANGUAGE as the USER REQUEST"""


PLAN_PROMPT_TEMPLATE = """Based on this task analysis, propose exactly 5 plan variants — from FASTEST to MAXIMUM QUALITY.

ORIGINAL REQUEST: "{topic}"

TASK ANALYSIS:
{analysis}

EXISTING AGENTS (reuse if suitable): {existing}

BASE MODES (can use as-is or combine into custom workflows):
- pipeline: Sequential handoff between agents
- discuss: All agents debate simultaneously in rounds
- parallel: Agents work on different subtasks at the same time
- consensus: Agents vote independently
- loop: Repeat a stage until quality criteria met (agent evaluates output, loops back if not good enough). In workflow: {{"type":"loop","agent":"evaluator_id","target_stage":0,"max_iterations":3,"criteria":"description of when to stop"}}

You can also design CUSTOM workflows by combining these in "options.workflow" — a sequence of stages:
  {{"workflow": [{{"type":"parallel","agents":["a","b"],"task":"research"}}, {{"type":"discuss","agents":["c","d"],"rounds":2}}, {{"type":"pipeline","steps":[{{"agent":"e","action":"write"}}]}}]}}

Return ONLY a valid JSON array of 5 plans:
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
    "options": {{"rounds": <number>}},
    "recommended": <true ONLY for the one variant you consider optimal for this task, false for others>
  }}
]

For "custom" mode, add "workflow" array in options describing stage-by-stage execution.
Mark exactly ONE variant as "recommended": true — the one with the best quality/speed tradeoff for THIS specific task.

CRITICAL — USE THE TASK ANALYSIS PHASES:
The task analysis above already identified the phases this task needs. USE THEM.
Build workflows that follow these phases. Use "custom" mode with workflow stages.
Each stage's agents get output from ALL previous stages as context.

Mix stage types freely based on what each phase needs:
  - Phase needs ideas? → parallel or discuss
  - Phase needs building/writing? → pipeline
  - Phase needs a decision? → consensus or discuss
  - Phase needs quality check? → loop
  - Phase needs research? → parallel

Example: "сделай сайт" →
  Stage 1: discuss (requirements + design decisions)
  Stage 2: pipeline (architect designs → developer codes)
  Stage 3: loop (reviewer checks → developer fixes)
  Stage 4: parallel (testing + documentation)

Example: "выбери лучшую идею" →
  Stage 1: parallel (3 agents brainstorm independently)
  Stage 2: discuss (debate the ideas, 2 rounds)
  Stage 3: consensus (vote on winner)

VARIANT RULES:
- The 5 variants must differ significantly in depth and approach
- Variant 1 = lightning fast, minimal agents, instant result, may sacrifice depth
- Variant 2 = quick but smarter, a bit more agents/steps for better quality
- Variant 3 = balanced, good tradeoff between speed and quality
- Variant 4 = thorough, more phases, deeper analysis, review loops
- Variant 5 = maximum quality, all phases, many agents, parallel exploration, multiple loops, opus models for key roles
- Do NOT use fixed numbers — adapt everything to the task
- Each variant MUST have its own interaction strategy. Describe step-by-step in "description"
- Choose models per agent based on role complexity

GENERAL RULES:
- For pipeline: add "steps" in options: [{{"agent":"id","action":"<verb>"}}]
- For parallel: add "tasks" in options: [{{"agent":"id","description":"subtask"}}]
- For loop: add in workflow: {{"type":"loop","agent":"id","target_stage":<N>,"max_iterations":3,"criteria":"..."}}
- Each agent's system_prompt must be specific to THIS task AND to their phase
- IMPORTANT: ALL text MUST be in the SAME LANGUAGE as the TASK"""


async def _call_claude(prompt: str, model: str = "opus", max_retries: int = 3) -> str:
    """Helper: call Claude with auto-retry on failure."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, ResultMessage, TextBlock

    fallback_models = {"opus": "sonnet", "sonnet": "haiku", "haiku": "haiku"}
    current_model = model

    for attempt in range(max_retries):
        try:
            options = ClaudeAgentOptions(model=current_model, max_turns=1, permission_mode="bypassPermissions")
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

            if content.strip():
                return content

            # Empty response — retry with fallback model
            print(f"Empty response from {current_model} (attempt {attempt+1})")
            current_model = fallback_models.get(current_model, current_model)

        except Exception as e:
            print(f"_call_claude error (attempt {attempt+1}, model={current_model}): {e}")
            current_model = fallback_models.get(current_model, current_model)
            if attempt == max_retries - 1:
                raise

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
    """Two-stage planning: analyze task, then generate 5 variants."""
    config = load_config(CONFIG_PATH)
    existing = {name: {"display_name": r.display_name, "model": r.model}
                for name, r in config.agents.items()}

    try:
        # Stage 1: Analyze the prompt
        analyze_prompt = ANALYZE_PROMPT.format(topic=req.topic)
        analysis_raw = await _call_claude(analyze_prompt, model="opus")
        if not analysis_raw.strip():
            return {"error": "Empty response from analysis stage"}
        try:
            analysis = _parse_json(analysis_raw)
        except Exception as e:
            print(f"Analysis parse error: {e}\nRaw: {analysis_raw[:500]}")
            return {"error": f"Failed to parse analysis: {e}"}

        # Stage 2: Generate plans based on analysis
        prompt = PLAN_PROMPT_TEMPLATE.format(
            topic=req.topic,
            analysis=json.dumps(analysis, ensure_ascii=False, indent=2),
            existing=json.dumps(existing),
        )
        content = await _call_claude(prompt, model="opus")
        if not content.strip():
            return {"error": "Empty response from planning stage"}
        try:
            plans = _parse_json(content)
        except Exception as e:
            print(f"Plans parse error: {e}\nRaw: {content[:500]}")
            return {"error": f"Failed to parse plans: {e}"}

        if not isinstance(plans, list):
            return {"error": f"Expected array of plans, got {type(plans).__name__}"}

        return {"analysis": analysis, "plans": plans}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@app.post("/api/auto-plan")
async def auto_plan(req: AutoPlanRequest):
    """Single plan (backward compat). Returns the balanced variant."""
    result = await auto_plans(req)
    if isinstance(result, dict) and result.get("error"):
        return result
    plans = result.get("plans", []) if isinstance(result, dict) else result
    if not plans:
        return {"error": "No plans generated"}
    # Return recommended or middle
    for p in plans:
        if p.get("recommended"):
            return p
    return plans[len(plans)//2]

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


from ..orchestrator.jobs import job_manager, Job


async def _run_job_task(job: Job):
    """Background task that runs the supervised orchestration."""
    from ..orchestrator.supervisor import SupervisedRun

    async def on_update(agent_name: str, event: str, text: str):
        if event == "start":
            active_agents[agent_name] = "working"
        elif event in ("done", "error"):
            active_agents[agent_name] = "idle"
        job.add_event(agent_name, event, text)

    try:
        supervised = SupervisedRun(goal=job.goal, on_update=on_update)
        result = await supervised.run()
        active_agents.clear()
        run_dir = save_run(result)
        job.finish("done", {
            "summary": result.summary,
            "cost": result.total_cost,
            "duration_ms": result.total_duration_ms,
            "responses": len(result.responses),
            "run_id": run_dir.name,
        })
    except asyncio.CancelledError:
        active_agents.clear()
        job.finish("stopped")
    except Exception as e:
        import traceback
        traceback.print_exc()
        active_agents.clear()
        job.add_event("System", "error", str(e))
        job.finish("error", {"error": str(e)})


# ── Job API ──

@app.get("/api/jobs")
async def list_jobs():
    return job_manager.list_all()


@app.get("/api/jobs/current")
async def current_job():
    job = job_manager.get_running()
    if job:
        return job.to_summary()
    return {"status": "idle"}


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    if job_manager.stop(job_id):
        return {"ok": True}
    return {"error": "Job not found or not running"}


# ── WebSocket ──

@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    await ws.accept()

    try:
        msg = await ws.receive_json()
        action = msg.get("action", "start")  # start | attach
        topic = msg.get("topic", "")
        job_id = msg.get("job_id")

        if action == "attach" and job_id:
            # Reconnect to existing job
            job = job_manager.get(job_id)
            if not job:
                await ws.send_json({"type": "error", "text": "Job not found"})
                return
            # Send all past events first (replay)
            for ev in job.events:
                await ws.send_json({"type": "update", "agent": ev.agent, "event": ev.event, "text": ev.text})
            if job.status != "running":
                # Job already finished
                await ws.send_json({"type": "result", **(job.result or {})})
                return
        elif action == "start":
            if not topic:
                await ws.send_json({"type": "error", "text": "No topic provided"})
                return
            # Check if already running
            existing = job_manager.get_running()
            if existing:
                await ws.send_json({"type": "error", "text": f"Job already running: {existing.id}"})
                return
            # Create background job
            job = job_manager.create(goal=topic)
            job._task = asyncio.create_task(_run_job_task(job))
            await ws.send_json({"type": "job_created", "job_id": job.id})
        else:
            await ws.send_json({"type": "error", "text": "Invalid action"})
            return

        # Subscribe to live events
        queue = job.subscribe()
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    # Job finished
                    await ws.send_json({"type": "result", **(job.result or {})})
                    break
                await ws.send_json({
                    "type": "update",
                    "agent": ev.agent,
                    "event": ev.event,
                    "text": ev.text,
                })
        finally:
            job.unsubscribe(queue)

    except WebSocketDisconnect:
        pass  # Job continues in background!
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await ws.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


def run_server(host: str = "0.0.0.0", port: int = 3025):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
