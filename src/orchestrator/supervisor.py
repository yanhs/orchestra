"""Supervisor — top-level controller that manages the entire execution."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..agents.client import AgentClient, AgentResponse
from ..agents.definition import AgentRole, load_config
from ..modes.base import OrchestraResult, UpdateCallback

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "agents.yaml"
LOG_DIR = Path(__file__).parent.parent.parent / "_orchestra" / "supervised"


async def _call_supervisor(prompt: str) -> str:
    """Call supervisor (opus) and get response."""
    from claude_agent_sdk import (
        ClaudeAgentOptions, ClaudeSDKClient,
        AssistantMessage, ResultMessage, TextBlock,
    )

    options = ClaudeAgentOptions(
        model="opus",
        max_turns=1,
        permission_mode="bypassPermissions",
    )
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
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


SUPERVISOR_SYSTEM = """You are a Supervisor — a top-level controller managing a team of AI agents.

YOUR ROLE:
- You hold the main GOAL and never lose sight of it
- You break the goal into stages
- For each stage you define which agents to create and how they should interact
- After each stage you review results and decide: continue / retry / change plan
- You do NOT do the work — you ONLY control and direct
- You MUST ALWAYS launch at least one stage with agents. NEVER finish without running agents.
- Even for simple tasks, create an agent to do the work. You are a manager, not a worker.

RESPONSE FORMAT — always return valid JSON:

To start a new stage:
{{
  "action": "run_stage",
  "stage_name": "<name>",
  "stage_goal": "<what this stage should achieve>",
  "mode": "<discuss|pipeline|parallel|consensus>",
  "agents": [
    {{
      "id": "<snake_case>",
      "display_name": "<name>",
      "model": "<opus|sonnet|haiku>",
      "max_turns": <N>,
      "allowed_tools": ["Read","Write","Edit","Bash","Glob","Grep","WebSearch","WebFetch"],
      "system_prompt": "<specific instructions for THIS stage>"
    }}
  ],
  "options": {{<mode-specific: rounds, steps, tasks>}},
  "reasoning": "<why this stage, why these agents>"
}}

To finish:
{{
  "action": "finish",
  "summary": "<final result addressing the original goal>",
  "reasoning": "<why we're done>"
}}

To retry a stage:
{{
  "action": "retry",
  "feedback": "<what was wrong, what to improve>",
  "modifications": "<changes to agents/mode/options>"
}}

RULES:
- Always respond in the same language as the goal
- Be strategic — don't waste stages on trivial things
- Each stage should produce clear deliverables
- Review results critically — don't accept low quality
- Maximum 10 stages total
- You can create ANY agents needed for each stage"""


class SupervisedRun:
    """Runs a task under supervisor control."""

    def __init__(
        self,
        goal: str,
        on_update: UpdateCallback | None = None,
        project_path: Path | None = None,
    ):
        self.goal = goal
        self.on_update = on_update
        self.project_path = project_path or Path.cwd()
        self.stages: list[dict] = []
        self.log: list[dict] = []
        self.max_stages = 10

    async def _notify(self, agent: str, event: str, text: str):
        if self.on_update:
            r = self.on_update(agent, event, text)
            if asyncio.iscoroutine(r):
                await r

    def _log(self, entry: dict):
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.log.append(entry)

    async def run(self) -> OrchestraResult:
        """Execute the full supervised workflow."""
        result = OrchestraResult(mode="supervised", topic=self.goal)

        # Initial prompt to supervisor
        prompt = f"""{SUPERVISOR_SYSTEM}

GOAL: "{self.goal}"

Plan your first stage. What should we do first to achieve this goal?"""

        await self._notify("Supervisor", "start", "Analyzing goal and planning first stage...")

        for stage_num in range(self.max_stages):
            # Ask supervisor what to do
            try:
                raw = await _call_supervisor(prompt)
                if not raw.strip():
                    await self._notify("Supervisor", "error", "Empty response, retrying...")
                    continue
                decision = _parse_json(raw)
            except Exception as e:
                await self._notify("Supervisor", "error", f"Parse error: {e}")
                self._log({"type": "error", "stage": stage_num, "error": str(e)})
                break

            action = decision.get("action", "")
            self._log({"type": "decision", "stage": stage_num, "decision": decision})

            if action == "finish":
                if not self.stages:
                    # Force at least one stage
                    prompt = f"""{SUPERVISOR_SYSTEM}

GOAL: "{self.goal}"

You tried to finish without running any agents. You MUST launch at least one stage.
You are a manager — delegate the work to agents. Plan a stage now."""
                    await self._notify("Supervisor", "start", "Must run agents first, replanning...")
                    continue
                result.summary = decision.get("summary", "")
                await self._notify("Supervisor", "done",
                    f"**Goal achieved**\n\n{decision.get('reasoning', '')}\n\n{result.summary}")
                break

            elif action == "retry":
                await self._notify("Supervisor", "start",
                    f"Retrying: {decision.get('feedback', '')}")
                # Rebuild prompt with feedback
                prompt = self._build_retry_prompt(decision)
                continue

            elif action == "run_stage":
                stage_name = decision.get("stage_name", f"Stage {stage_num + 1}")
                await self._notify("Supervisor", "done",
                    f"**Stage {stage_num + 1}: {stage_name}**\n{decision.get('reasoning', '')}")

                # Execute the stage
                stage_result = await self._execute_stage(decision, stage_num)
                self.stages.append({
                    "name": stage_name,
                    "decision": decision,
                    "result_summary": stage_result.summary or "",
                    "responses": [r.content[:500] for r in stage_result.responses if not r.is_error],
                })

                # Add responses to main result
                for resp in stage_result.responses:
                    result.add_response(resp)

                # Build prompt for next supervisor decision
                stage_output = stage_result.summary or "\n".join(
                    f"[{r.agent_name}]: {r.content[:1000]}"
                    for r in stage_result.responses if not r.is_error
                )
                prompt = self._build_next_prompt(stage_num, stage_name, stage_output)

                await self._notify("Supervisor", "start", "Reviewing results, planning next stage...")

            else:
                await self._notify("Supervisor", "error", f"Unknown action: {action}")
                break

        # Save full log
        self._save_log()

        return result

    async def _execute_stage(self, decision: dict, stage_num: int) -> OrchestraResult:
        """Execute a single stage using the coordinator."""
        from .coordinator import OrchestraCoordinator

        mode = decision.get("mode", "discuss")
        agents_data = decision.get("agents", [])
        options = decision.get("options", {})

        # Create agents in config
        config = load_config(CONFIG_PATH)

        import yaml
        raw = {}
        with open(CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}
        if "agents" not in raw:
            raw["agents"] = {}

        for ag in agents_data:
            raw["agents"][ag["id"]] = {
                "display_name": ag.get("display_name", ag["id"]),
                "model": ag.get("model", "sonnet"),
                "system_prompt": ag.get("system_prompt", ""),
                "allowed_tools": ag.get("allowed_tools", []),
                "max_turns": ag.get("max_turns", 30),
            }
        with open(CONFIG_PATH, "w") as f:
            yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        # Reload and run
        config = load_config(CONFIG_PATH)
        coordinator = OrchestraCoordinator(
            config=config,
            project_path=self.project_path,
        )

        agent_ids = [a["id"] for a in agents_data]

        if mode == "discuss":
            return await coordinator.discuss(
                topic=self.goal,
                agent_names=agent_ids,
                rounds=options.get("rounds", 2),
                on_update=self.on_update,
            )
        elif mode == "pipeline":
            steps = options.get("steps", [{"agent": a, "action": "process"} for a in agent_ids])
            return await coordinator.pipeline(
                topic=self.goal,
                steps=[(s["agent"], s["action"]) for s in steps],
                on_update=self.on_update,
            )
        elif mode == "parallel":
            tasks = options.get("tasks", [{"agent": a, "description": "work"} for a in agent_ids])
            return await coordinator.parallel(
                topic=self.goal,
                tasks=[(t["agent"], t["description"]) for t in tasks],
                on_update=self.on_update,
            )
        elif mode == "consensus":
            return await coordinator.consensus(
                topic=self.goal,
                agent_names=agent_ids,
                on_update=self.on_update,
            )
        elif mode == "custom":
            workflow = options.get("workflow", [])
            return await coordinator.custom(
                topic=self.goal,
                workflow=workflow,
                on_update=self.on_update,
            )
        else:
            return OrchestraResult(mode=mode, topic=self.goal)

    def _build_next_prompt(self, stage_num: int, stage_name: str, output: str) -> str:
        history = "\n".join(
            f"Stage {i+1} ({s['name']}): completed"
            for i, s in enumerate(self.stages)
        )
        return f"""{SUPERVISOR_SYSTEM}

GOAL: "{self.goal}"

COMPLETED STAGES:
{history}

LATEST STAGE RESULTS ({stage_name}):
{output[:3000]}

Based on these results, what should we do next? Are we closer to the goal?
If the goal is achieved, use "finish". If more work needed, plan the next stage."""

    def _build_retry_prompt(self, decision: dict) -> str:
        feedback = decision.get("feedback", "")
        return f"""{SUPERVISOR_SYSTEM}

GOAL: "{self.goal}"

PREVIOUS ATTEMPT FAILED. FEEDBACK: {feedback}

Modifications requested: {decision.get('modifications', 'none')}

Plan a corrected stage."""

    def _save_log(self):
        """Save full execution log to disk."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_file = LOG_DIR / f"{ts}.json"
        log_data = {
            "goal": self.goal,
            "stages": self.stages,
            "log": self.log,
            "timestamp": ts,
        }
        log_file.write_text(json.dumps(log_data, indent=2, ensure_ascii=False))
