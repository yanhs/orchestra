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


async def _call_claude(prompt: str, model: str = "opus", max_retries: int = 3, system_prompt: str = "", on_progress=None, max_turns: int = 1) -> str:
    """Helper: call Claude with auto-retry and token-level streaming."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, ResultMessage, TextBlock
    try:
        from claude_agent_sdk import StreamEvent
    except ImportError:
        StreamEvent = None

    fallback_models = {"opus": "sonnet", "sonnet": "haiku", "haiku": "haiku"}
    requested_model = model
    current_model = model

    for attempt in range(max_retries):
        try:
            options = ClaudeAgentOptions(model=current_model, max_turns=max_turns, permission_mode="bypassPermissions")
            if system_prompt:
                options.system_prompt = system_prompt
            # Enable token-level streaming
            options.include_partial_messages = True
            client = ClaudeSDKClient(options)
            content = ""
            stream_buf = ""  # accumulate deltas for progress
            try:
                await client.connect()
                await client.query(prompt)
                async for msg in client.receive_messages():
                    if isinstance(msg, ResultMessage):
                        if msg.result:
                            content = msg.result
                        break
                    elif StreamEvent and isinstance(msg, StreamEvent):
                        # Token-level streaming
                        ev = msg.event if isinstance(msg.event, dict) else {}
                        delta = ev.get('delta', {})
                        if delta.get('type') == 'text_delta':
                            chunk = delta.get('text', '')
                            stream_buf += chunk
                            content += chunk
                            # Send progress every ~100 chars
                            if on_progress and len(stream_buf) >= 100:
                                r = on_progress(stream_buf)
                                if asyncio.iscoroutine(r): await r
                                stream_buf = ""
                    elif isinstance(msg, AssistantMessage):
                        # Full message (fallback if StreamEvent not available)
                        msg_text = ""
                        for block in msg.content or []:
                            if isinstance(block, TextBlock):
                                msg_text += block.text
                                if not stream_buf:  # only add if not already from deltas
                                    content += block.text
                        if on_progress and msg_text and not stream_buf:
                            r = on_progress(msg_text)
                            if asyncio.iscoroutine(r): await r
                # Flush remaining buffer
                if on_progress and stream_buf:
                    r = on_progress(stream_buf)
                    if asyncio.iscoroutine(r): await r
            finally:
                await client.disconnect()

            if content.strip():
                # Warn if model was downgraded
                if current_model != requested_model:
                    content = f"[WARNING: responded by {current_model}, not {requested_model}]\n{content}"
                return content

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

    # Store agent configs on the job for direct messaging
    if not hasattr(job, '_agent_configs'):
        job._agent_configs = {}

    async def on_update(agent_name: str, event: str, text: str):
        if event == "start":
            active_agents[agent_name] = "working"
        elif event in ("done", "error"):
            active_agents[agent_name] = "idle"
        elif event == "agent_config":
            # Store agent config for direct messaging later
            try:
                cfg = json.loads(text)
                for ag_id, ag_data in cfg.items():
                    job._agent_configs[ag_id] = ag_data
            except Exception:
                pass
            return  # Don't broadcast config events to frontend
        job.add_event(agent_name, event, text)
        # Keep context_doc + checkpoint synced for continuation
        if hasattr(supervised, 'context_doc'):
            job._context_doc = supervised.context_doc
            job._total_cost = supervised.total_cost
            job._run_dir = str(supervised.run_dir)
            # Save checkpoint on every stage completion (agent "done" from supervisor level)
            if event == "done" and (agent_name.startswith("Manager") or agent_name == "Executive"):
                try: supervised._save_progress()
                except: pass

    try:
        supervisor_model = getattr(job, 'supervisor_model', 'sonnet')
        full_topic = getattr(job, '_full_topic', job.goal)

        # Try to resume from checkpoint if continuing
        prev_run_dir = getattr(job, '_prev_run_dir', '')
        checkpoint = Path(prev_run_dir) / '.checkpoint.json' if prev_run_dir else None
        if checkpoint and checkpoint.exists():
            supervised = SupervisedRun.from_checkpoint(checkpoint, on_update=on_update)
            supervised.supervisor_model = supervisor_model
            supervised.goal = full_topic  # may have new instructions
        else:
            supervised = SupervisedRun(goal=full_topic, on_update=on_update, supervisor_model=supervisor_model)
            # Inherit context from previous job (continuation)
            prev_ctx = getattr(job, '_prev_context', '')
            if prev_ctx:
                supervised.context_doc = prev_ctx
                supervised.total_cost = getattr(job, '_prev_cost', 0.0)
        # Link feedback queues so user corrections flow through
        job._feedback_queue = supervised.feedback_queue
        # Link job for child task tracking + run_dir for resume
        supervised._job = job
        job._run_dir = str(supervised.run_dir)
        result = await supervised.run()
        active_agents.clear()
        run_dir = save_run(result)
        # Save state for continuation (always, even before finish)
        job._context_doc = supervised.context_doc
        job._run_dir = str(supervised.run_dir)
        job._total_cost = supervised.total_cost
        job.finish("done", {
            "summary": result.summary,
            "cost": result.total_cost,
            "duration_ms": result.total_duration_ms,
            "responses": len(result.responses),
            "run_id": run_dir.name,
        })
    except asyncio.CancelledError:
        active_agents.clear()
        # Save checkpoint + preserve context for resume
        try: supervised._save_progress()
        except: pass
        job._context_doc = getattr(supervised, 'context_doc', '')
        job._total_cost = getattr(supervised, 'total_cost', 0.0)
        job._run_dir = str(getattr(supervised, 'run_dir', ''))
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
    running = job_manager.get_all_running()
    if running:
        return {"status": "running", "jobs": [j.to_summary() for j in running]}
    return {"status": "idle", "jobs": []}


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    if job_manager.stop(job_id):
        return {"ok": True}
    return {"error": "Job not found or not running"}

@app.post("/api/jobs/resume")
async def resume_job():
    """Resume the most recent checkpoint."""
    from ..orchestrator.supervisor import SupervisedRun
    import glob as glob_mod
    runs_dir = Path(__file__).parent.parent.parent / "_orchestra" / "runs"
    checkpoints = sorted(runs_dir.glob("*/.checkpoint.json"), key=lambda p: -p.stat().st_mtime)
    if not checkpoints:
        return {"error": "No checkpoints found"}
    return {"checkpoint": str(checkpoints[0]), "goal": json.loads(checkpoints[0].read_text()).get("goal", "")}

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        return {"error": "Job not found"}
    if job.status == "running":
        job_manager.stop(job_id)
    del job_manager.jobs[job_id]
    # Also delete from disk so it doesn't reload
    disk_file = Path(__file__).parent.parent.parent / "_orchestra" / "jobs" / f"{job_id}.json"
    if disk_file.exists():
        disk_file.unlink()
    return {"ok": True}


# ── WebSocket ──

async def _handle_message_agent(job: Job, agent_id: str, text: str):
    """Send a direct message to a specific agent and stream response back."""
    from ..agents.client import AgentClient
    from ..agents.definition import AgentRole

    # Find agent config — search by id first, then by display_name
    agent_data = None
    actual_id = agent_id
    if hasattr(job, '_agent_configs'):
        if agent_id in job._agent_configs:
            agent_data = job._agent_configs[agent_id]
        else:
            # Search by display_name
            for aid, adata in job._agent_configs.items():
                if adata.get("display_name") == agent_id:
                    agent_data = adata
                    actual_id = aid
                    break
    if not agent_data:
        try:
            config = load_config(CONFIG_PATH)
            if agent_id in config.agents:
                role = config.agents[agent_id]
                agent_data = {
                    "display_name": role.display_name,
                    "model": role.model,
                    "system_prompt": role.system_prompt,
                    "allowed_tools": role.allowed_tools,
                    "max_turns": role.max_turns,
                }
            else:
                for aid, role in config.agents.items():
                    if role.display_name == agent_id:
                        agent_data = {
                            "display_name": role.display_name,
                            "model": role.model,
                            "system_prompt": role.system_prompt,
                            "allowed_tools": role.allowed_tools,
                            "max_turns": role.max_turns,
                        }
                        actual_id = aid
                        break
        except Exception:
            pass
    agent_id = actual_id

    if not agent_data:
        job.add_event("System", "error", f"Agent '{agent_id}' not found")
        return

    display_name = agent_data.get("display_name", agent_id)

    # Show user message
    job.add_event("User", "feedback", f"[to {display_name}]: {text}")

    role = AgentRole(
        name=agent_id,
        display_name=display_name,
        model=agent_data.get("model", "sonnet"),
        system_prompt=agent_data.get("system_prompt", ""),
        allowed_tools=agent_data.get("allowed_tools", []),
        max_turns=agent_data.get("max_turns", 50),
    )

    client = AgentClient(role=role)

    async def on_stream(agent_name: str, chunk: str):
        job.add_event(agent_name, "progress", chunk)

    job.add_event(display_name, "start", f"Processing: {text[:100]}...")

    try:
        resp = await client.run(prompt=text, on_stream=on_stream)
        if resp.is_error:
            job.add_event(display_name, "error", resp.error_message)
        else:
            job.add_event(display_name, "done", resp.content)
    except Exception as e:
        job.add_event(display_name, "error", str(e))


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
                # Job finished — send result but stay open for direct agent messaging
                await ws.send_json({"type": "result", **(job.result or {})})
                # Listen for direct agent messages
                queue = job.subscribe()
                async def _send_new():
                    while True:
                        ev = await queue.get()
                        if ev is None: break
                        await ws.send_json({"type":"update","agent":ev.agent,"event":ev.event,"text":ev.text})
                async def _recv_msg():
                    while True:
                        try:
                            m = await ws.receive_json()
                            if m.get("action")=="message_agent" and m.get("agent_id") and m.get("text"):
                                asyncio.create_task(_handle_message_agent(job, m["agent_id"], m["text"]))
                        except (WebSocketDisconnect, Exception):
                            return
                try:
                    s=asyncio.create_task(_send_new())
                    r=asyncio.create_task(_recv_msg())
                    await asyncio.wait([s,r],return_when=asyncio.FIRST_COMPLETED)
                    for t in [s,r]:
                        if not t.done(): t.cancel()
                finally:
                    job.unsubscribe(queue)
                return
        elif action == "start":
            if not topic:
                await ws.send_json({"type": "error", "text": "No topic provided"})
                return
            # Create background job (multiple jobs can run concurrently)
            supervisor_model = msg.get("supervisor_model", "sonnet")
            continue_from = msg.get("continue_from")
            # Use display_goal from frontend (most reliable), fallback to regex cleanup
            import re
            display_goal = msg.get("display_goal", "")
            clean_goal = display_goal or re.sub(r'^Continue:?\s*".*?"\s*\n*\s*(New instruction:\s*)?', '', topic).strip() or topic
            job = job_manager.create(goal=clean_goal)
            job._full_topic = topic
            job.supervisor_model = supervisor_model
            # Inherit context + original goal from previous job for continuation
            if continue_from:
                prev = job_manager.get(continue_from)
                if prev:
                    job._prev_context = getattr(prev, '_context_doc', '')
                    job._prev_run_dir = getattr(prev, '_run_dir', '')
                    job._prev_cost = getattr(prev, '_total_cost', 0.0)
                    job._prev_goal = prev.goal
                    # Use previous job's goal as display name (not "продолжай")
                    if prev.goal and prev.goal != clean_goal:
                        job.goal = prev.goal
            job._task = asyncio.create_task(_run_job_task(job))
            await ws.send_json({"type": "job_created", "job_id": job.id})
        else:
            await ws.send_json({"type": "error", "text": "Invalid action"})
            return

        # Subscribe to live events + listen for user corrections (bidirectional)
        queue = job.subscribe()

        async def _send_events():
            """Forward job events to WebSocket."""
            while True:
                ev = await queue.get()
                if ev is None:
                    await ws.send_json({"type": "result", **(job.result or {})})
                    return
                await ws.send_json({
                    "type": "update",
                    "agent": ev.agent,
                    "event": ev.event,
                    "text": ev.text,
                })

        async def _recv_feedback():
            """Listen for user corrections mid-run and direct agent messages."""
            while True:
                try:
                    msg = await ws.receive_json()
                    if msg.get("action") == "feedback" and msg.get("text"):
                        job.add_feedback(msg["text"])
                    elif msg.get("action") == "message_agent":
                        agent_id = msg.get("agent_id", "")
                        text = msg.get("text", "")
                        if agent_id and text:
                            asyncio.create_task(_handle_message_agent(job, agent_id, text))
                except WebSocketDisconnect:
                    return
                except Exception:
                    pass  # Don't kill on parse errors etc — keep listening

        try:
            # Run both tasks concurrently — first to finish wins
            send_task = asyncio.create_task(_send_events())
            recv_task = asyncio.create_task(_recv_feedback())
            done, pending = await asyncio.wait(
                [send_task, recv_task], return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
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
