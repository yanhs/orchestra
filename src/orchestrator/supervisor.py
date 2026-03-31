"""Supervisor — top-level controller that manages the entire execution."""

import asyncio
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..agents.client import AgentClient, AgentResponse
from ..agents.definition import AgentRole, load_config
from ..modes.base import OrchestraResult, UpdateCallback

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "agents.yaml"
LOG_DIR = Path(__file__).parent.parent.parent / "_orchestra" / "supervised"
_config_lock = asyncio.Lock()


async def _call_supervisor(prompt: str, model: str = "sonnet", on_progress=None) -> str:
    """Call supervisor with streaming progress."""
    from ..web.server import _call_claude
    return await _call_claude(prompt, model=model, max_turns=3,
        system_prompt="Think step by step about the task, then respond with a valid JSON object. Your thinking will be shown to the user as progress.",
        on_progress=on_progress)


def _parse_json(text: str):
    text = text.strip()
    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    # Strip [WARNING:...] prefix
    if text.startswith("[WARNING:"):
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl+1:].strip()
    # Find JSON object boundaries if there's surrounding text (prefer { over [)
    if text and text[0] != '{':
        start = text.find('{')
        if start >= 0:
            text = text[start:]
        elif text[0] != '[':
            start = text.find('[')
            if start >= 0:
                text = text[start:]
    if text and text[-1] not in ('}', ']'):
        for end_char in ('}', ']'):
            end = text.rfind(end_char)
            if end >= 0:
                text = text[:end+1]
                break
    return json.loads(text)


SUPERVISOR_SYSTEM = """You are an Executive — the top-level controller of a hierarchical team.

YOUR ROLE:
- You hold the main GOAL and never lose sight of it
- You create MANAGERS for major directions — each manager runs independently with their own workers
- You review manager results, coordinate between directions, decide strategy
- You do NOT do the work and do NOT create workers directly — delegate to managers
- You MUST ALWAYS launch at least one stage or delegation. NEVER finish without real work done.

HIERARCHY:
  Executive (you) → creates Managers via "delegate"
  Manager → creates Workers (agents), chooses orchestration patterns
  Worker → executes tasks, can request help via [REQUEST_AGENT: role description]

WHEN TO USE HIERARCHY:
- If the user asks for multiple teams/groups/directions → ALWAYS delegate each to a separate Manager
- If the task has 2+ independent parts → delegate each part to a Manager
- Only use "run_stage" directly for truly trivial one-step tasks (e.g. "2+2")
- When in doubt → delegate. Managers handle complexity, you handle strategy.
- You can run multiple "delegate" actions via "run_parallel_stages" for parallel teams.

CRITICAL: A plan is NOT a result. Agents must EXECUTE — write code, create files, take real actions. Only finish when work is done.
CRITICAL: For code tasks — always include a testing stage. Agents must write and run tests (pytest/unittest). Untested code is not done.

BASE MODES (building blocks):

parallel — agents work independently on separate tasks, results collected at the end
  Options: "tasks" — list of {{agent, description}} pairs

discuss — agents see each other's output and respond in rounds
  Options: "rounds" — number of rounds (1-3)

pipeline — sequential: output of one agent feeds the next
  Options: "steps" — ordered list of {{agent, action}} pairs

consensus — agents vote independently on a question
  Options: defaults are fine

COMPOSITE STRATEGIES (build from base modes across multiple stages):

Red-Blue — adversarial quality loop:
  Stage 1 (pipeline): Blue agent builds/implements
  Stage 2 (discuss): Red agent attacks, finds flaws, Blue defends
  Stage 3 (pipeline): Blue fixes all issues
  Repeat stages 2-3 until Red finds nothing. Reuse agent IDs for memory.

MCTS-lite — explore then exploit:
  Stage 1 (parallel): 3+ agents quickly sketch different solutions (haiku, low max_turns)
  Stage 2 (consensus): agents vote on which approach is best
  Stage 3 (pipeline): best approach executed deeply (opus/sonnet, high max_turns)

Full Dev Team — iterative development cycle:
  Stage 1 (pipeline): architect designs → developer implements
  Stage 2 (parallel): tester writes+runs tests, reviewer does code review
  Stage 3 (pipeline): developer fixes all issues from tester+reviewer
  Repeat stages 2-3 until both tester and reviewer approve. Reuse agent IDs.

Tree of Thoughts — parallel exploration, pick winner:
  Stage 1 (parallel): 2-3 agents explore different approaches
  Stage 2 (discuss): agents compare and debate approaches
  Pick the best, continue with it.

You can invent your own composite strategies. These are examples, not a fixed list.

MECHANICS:

- "stage_topic": refine the topic for agents at each stage — incorporate what you've learned, don't just repeat the original goal.
- "context_update": after each stage, write KEY FINDINGS to carry forward. This builds a shared document all future agents see.
- "max_stages": set the stage budget (4-20), reassess as you go.
- "phase": free-form label for what this stage is doing (e.g. "research", "implementation", "evaluation" — whatever fits).
- "timeout": optional seconds limit per stage. Stage auto-aborts if exceeded.
- Models: haiku (fast/cheap), sonnet (balanced), opus (max quality). You decide.
- Agent sessions: if you reuse the same agent "id" across stages, the agent REMEMBERS everything from previous stages. Use this for continuity.
- All agent outputs are saved to files. You'll see file paths in stage results — agents can Read these files to access full previous work.
- For complex sub-goals, use action "delegate" to spawn a sub-supervisor (up to 5 stages).
- You can run multiple stages at once: use action "run_parallel_stages" with a "stages" array.

RESPONSE FORMAT — ONLY valid JSON, nothing else. No text before or after. No explanations. Just one JSON object:

To run a stage:
{{
  "action": "run_stage",
  "phase": "<free-form label for this stage>",
  "stage_name": "<name>",
  "stage_goal": "<what this stage should achieve>",
  "stage_topic": "<refined topic for agents>",
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
  "context_update": "<key findings to carry forward>",
  "max_stages": <4-20>,
  "reasoning": "<your reasoning>",
  "choices": ["<REQUIRED: always list 2-4 alternative approaches. User sees these as buttons. Example: ['Build SaaS app', 'Create digital product', 'Freelance service']>"]
}}

To finish:
{{
  "action": "finish",
  "summary": "<final result addressing the original goal>",
  "reasoning": "<why we're done — what was achieved across all strategies>"
}}

To correct and rerun a stage (steer):
{{
  "action": "steer",
  "feedback": "<what was wrong, specific corrections>",
  "stage_index": <which stage to rerun, 0-based>,
  "modifications": "<changes to agents/mode/options, or 'none' to keep same setup>"
}}

To retry with completely different approach:
{{
  "action": "retry",
  "feedback": "<what was wrong, what to improve>",
  "modifications": "<changes to agents/mode/options>"
}}

To delegate a sub-goal to a Manager:
{{
  "action": "delegate",
  "sub_goal": "<specific sub-goal for the manager>",
  "max_sub_stages": <3-5>,
  "manager_model": "<opus|sonnet|haiku>",
  "reasoning": "<why this needs its own manager>"
}}

To delegate multiple sub-goals in parallel (one Manager per sub-goal):
{{
  "action": "parallel_delegates",
  "delegates": [
    {{"sub_goal": "<sub-goal 1>", "max_sub_stages": <3-5>, "manager_model": "<model>"}},
    {{"sub_goal": "<sub-goal 2>", "max_sub_stages": <3-5>, "manager_model": "<model>"}}
  ],
  "reasoning": "<why parallel managers>"
}}

To run multiple stages in parallel:
{{
  "action": "run_parallel_stages",
  "stages": [<array of run_stage objects without "action" field>],
  "reasoning": "<why parallel>"
}}

RULES:
- Always respond in the same language as the goal. Agent names, their output, reasoning — EVERYTHING must be in the goal's language
- When creating agents: display_name and system_prompt MUST be in the goal's language
- Be strategic — don't waste stages on trivial things
- Each stage should produce clear deliverables
- Review results critically — don't accept low quality
- You can create ANY agents needed for each stage
- Reuse agent IDs across stages when you want them to remember previous work
- ALWAYS include "choices" field with 2-4 alternative approaches when starting a stage. The user sees these as clickable buttons and can redirect you. Don't stop — keep going with your best choice."""


MANAGER_SYSTEM = """You are a Manager — you run a TEAM of workers to achieve a specific sub-goal.

YOUR ROLE:
- You receive a SUB-GOAL from your Executive and must deliver results
- You create TEAMS of workers, not solo agents. Every stage should have 2+ agents with different roles.
- You choose the best orchestration pattern for each stage
- For very complex sub-tasks, delegate to a sub-manager via "delegate"
- Workers can request help: if you see [REQUEST_AGENT: ...] in their output, create the requested agent in the next stage

TEAM BUILDING RULES:
- MINIMUM 3 agents per stage. Never 1 or 2. This applies to EVERY stage including parallel sub-stages.
- Do NOT use run_parallel_stages with 1 agent per sub-stage. That defeats the purpose.
- Research/Analysis → 3+ agents: Researcher + Critic + Analyst (discuss mode, 2 rounds)
- Planning/Strategy → 3 agents: Strategist + Opponent/Devil's Advocate + Finalizer (Red-Blue or discuss)
- Development/Code → 4 agents: Architect → Developer → Tester → Reviewer (pipeline with rework)
- Content/Writing → 3 agents: Writer + Editor + Fact-checker (pipeline or Red-Blue)
- Every team MUST include a quality checker (critic/reviewer/tester) — no work ships without review.
- For implementation: use pipeline (architect→developer→tester→reviewer), NOT a single "Full-Stack Developer".
- If the goal mentions N items to build, create N parallel_delegates (sub-managers), each with a full team.

""" + SUPERVISOR_SYSTEM.split("BASE MODES")[1]  # Reuse modes, mechanics, format from main prompt


class SupervisedRun:
    """Runs a task under supervisor control."""

    @classmethod
    def from_checkpoint(cls, checkpoint_path: Path, on_update=None) -> "SupervisedRun":
        """Resume a run from a saved checkpoint."""
        data = json.loads(checkpoint_path.read_text())
        run = cls(
            goal=data["goal"],
            on_update=on_update,
            supervisor_model=data.get("supervisor_model", "sonnet"),
            level=data.get("level", 0),
        )
        run.context_doc = data.get("context_doc", "")
        run.phase_history = data.get("phase_history", [])
        run.current_phase = data.get("current_phase", "")
        run.total_cost = data.get("total_cost", 0.0)
        run.max_stages = data.get("max_stages", 10)
        run.stages = data.get("stages", [])
        # Restore agent hierarchy if saved
        saved_hierarchy = data.get("agent_hierarchy")
        if saved_hierarchy and isinstance(saved_hierarchy, dict):
            run.agent_hierarchy = saved_hierarchy
        # Use the same run_dir
        run.run_dir = checkpoint_path.parent
        return run

    def __init__(
        self,
        goal: str,
        on_update: UpdateCallback | None = None,
        project_path: Path | None = None,
        supervisor_model: str = "sonnet",
        level: int = 0,  # 0=executive, 1=manager, 2+=sub-manager
    ):
        self.goal = goal
        self.on_update = on_update
        self.project_path = project_path or Path.cwd()
        self.supervisor_model = supervisor_model
        self.level = level
        if level == 0:
            self.role_name = "Executive"
        else:
            # Unique name from goal
            short_goal = goal[:20].strip().replace('"','').replace('\n',' ')
            self.role_name = f"Manager: {short_goal}"
        self._system_prompt = SUPERVISOR_SYSTEM if level == 0 else MANAGER_SYSTEM
        self.stages: list[dict] = []
        self.log: list[dict] = []
        self.max_stages = 10
        self.current_phase: str = "research"
        self.phase_history: list[str] = []
        self.context_doc: str = ""  # shared context accumulating across phases
        self.feedback_queue: asyncio.Queue = asyncio.Queue()  # live user corrections
        self._job = None  # linked Job for child task tracking
        self.total_cost: float = 0.0
        # Agent hierarchy: key=display_name, value={parent, level, children}
        self.agent_hierarchy: dict[str, dict] = {
            self.role_name: {"parent": None, "level": self.level, "children": []}
        }
        self._parent_hierarchy: dict[str, dict] = {}  # inherited from parent supervisor
        # Directory for saving full agent outputs — inside project_path so agents can access
        run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.run_dir: Path = self.project_path / "_orchestra" / "runs" / f"{run_ts}_supervised"
        self.run_dir.mkdir(parents=True, exist_ok=True)

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

        # Check for sub-supervisor checkpoints to resume directly (skip Executive)
        if self.context_doc and not self.stages:
            import glob
            sub_checkpoints = sorted(
                glob.glob(str(self.project_path / "_orchestra" / "runs" / "*_supervised" / ".checkpoint.json")),
                key=lambda p: Path(p).stat().st_mtime, reverse=True
            )
            # Find sub-supervisors with actual stages (managers that did work)
            resumable = []
            for cp_path in sub_checkpoints[:10]:
                try:
                    cp_data = json.loads(Path(cp_path).read_text())
                    if cp_data.get("stages") and cp_data.get("goal") != self.goal:
                        resumable.append(cp_path)
                except: pass

            if resumable:
                await self._notify(self.role_name, "start",
                    f"Resuming {len(resumable)} manager(s) directly...")
                for cp_path in resumable:
                    try:
                        sub_run = SupervisedRun.from_checkpoint(Path(cp_path), on_update=self.on_update)
                        sub_run._parent_hierarchy = copy.deepcopy({**self._parent_hierarchy, **self.agent_hierarchy})
                        sub_result = await sub_run.run()
                        for resp in sub_result.responses:
                            result.add_response(resp)
                        self.total_cost += sub_run.total_cost
                        if sub_run.context_doc:
                            self.context_doc = sub_run.context_doc
                        # Merge hierarchy
                        for name, info in sub_run.agent_hierarchy.items():
                            if name not in self.agent_hierarchy:
                                self.agent_hierarchy[name] = info
                    except Exception as e:
                        await self._notify(self.role_name, "error", f"Resume failed: {e}")

                self._save_progress()
                # After resuming managers, let Executive decide what's next
                # (fall through to normal flow with updated context)

        if self.stages:
            # Resuming from checkpoint with completed stages
            last = self.stages[-1]
            await self._notify(self.role_name, "start",
                f"Resuming from stage {len(self.stages)} ({last['name']})...")
            prompt = self._build_next_prompt(
                len(self.stages) - 1, last["name"],
                last.get("result_summary", "Stage completed"))
            if self.agent_hierarchy:
                await self._notify(self.role_name, "hierarchy", json.dumps({**self._parent_hierarchy, **self.agent_hierarchy}))
        elif self.context_doc:
            # No completed stages but have context from previous decisions — CONTINUE, don't restart
            await self._notify(self.role_name, "start",
                "Continuing from previous progress...")
            # Find existing agents with sessions
            from ..orchestrator.sessions import load_sessions
            existing_sessions = load_sessions()
            existing_agents = [k for k in existing_sessions.keys() if not k.startswith('_')]
            agents_info = ""
            if existing_agents:
                agents_info = f"\n\nEXISTING AGENTS (already have sessions, REUSE their IDs — they remember everything):\n" + "\n".join(f"- {a}" for a in existing_agents[:20])

            # Find hierarchy info
            hier_info = ""
            if self.agent_hierarchy and len(self.agent_hierarchy) > 1:
                hier_info = "\n\nEXISTING HIERARCHY:\n"
                for name, info in self.agent_hierarchy.items():
                    ch = info.get('children', [])
                    hier_info += f"- {name} (L{info.get('level',0)}){' → ' + ', '.join(ch) if ch else ''}\n"

            prompt = f"""{self._system_prompt}

GOAL: "{self.goal}"

PREVIOUS PROGRESS (was interrupted, continue from here):
{self.context_doc}
{agents_info}
{hier_info}
IMPORTANT: Do NOT create new agents or managers. The agents above already exist with full memory. Reuse their exact IDs to continue their work. If managers were already delegated — re-delegate to the SAME managers. Respond with a JSON object."""
        else:
            # Fresh start
            prompt = f"""{self._system_prompt}

GOAL: "{self.goal}"

Respond with a JSON object. Plan your first stage."""
            await self._notify(self.role_name, "start", "Analyzing goal...")

        empty_retries = 0
        max_empty_retries = 3
        parse_retries = 0

        for stage_num in range(self.max_stages):
            # Check if we've already consumed enough stages (parallel stages add multiple)
            if len(self.stages) >= self.max_stages:
                break

            # Check for live user corrections (non-blocking)
            user_corrections = []
            while not self.feedback_queue.empty():
                try:
                    fb = self.feedback_queue.get_nowait()
                    user_corrections.append(fb)
                except asyncio.QueueEmpty:
                    break
            if user_corrections:
                corrections_text = "\n".join(f"- {c}" for c in user_corrections)
                prompt += f"\n\nUSER CORRECTION (live feedback, high priority):\n{corrections_text}\nAdjust your plan according to this feedback."
                await self._notify(self.role_name, "start", f"User correction received: {corrections_text[:200]}")

            # Ask supervisor what to do
            try:
                async def _sv_progress(text):
                    t = text.strip()
                    if t.startswith('{') or t.startswith('"') or t.startswith('[') or t.startswith('```'):
                        return
                    await self._notify(self.role_name, "progress", text)
                raw = await _call_supervisor(prompt, self.supervisor_model, on_progress=_sv_progress)
                if not raw.strip():
                    empty_retries += 1
                    if empty_retries > max_empty_retries:
                        await self._notify(self.role_name, "error", "Supervisor not responding. Stopping.")
                        break
                    await self._notify(self.role_name, "error", f"Empty response, retrying ({empty_retries}/{max_empty_retries})...")
                    continue
                empty_retries = 0  # reset on success
                # Strip model fallback warning before parsing JSON
                if raw.startswith("[WARNING:"):
                    warn_end = raw.find("]\n")
                    if warn_end > 0:
                        await self._notify(self.role_name, "error", raw[:warn_end+1])
                        raw = raw[warn_end+2:]
                decision = _parse_json(raw)
            except Exception as e:
                parse_retries += 1
                # Log raw response for debugging
                raw_preview = raw[:500] if raw else "(empty)"
                (self.run_dir / f"parse_error_{stage_num}_{parse_retries}.txt").write_text(
                    f"Error: {e}\n\nRaw response:\n{raw}", encoding="utf-8")
                await self._notify(self.role_name, "error",
                    f"Parse error ({parse_retries}/3): {e}\nRaw: {raw_preview[:100]}")
                self._log({"type": "error", "stage": stage_num, "error": str(e), "raw": raw_preview})
                if parse_retries >= 3:
                    await self._notify(self.role_name, "error", "Too many parse errors. Stopping.")
                    break
                # Retry — include the raw response so model can see what went wrong
                prompt = f'{self._system_prompt}\n\nGOAL: "{self.goal}"\n\nYour previous response was not valid JSON:\n{raw_preview}\n\nReturn ONLY a valid JSON object. No markdown fences, no explanation.'
                continue

            action = decision.get("action", "")
            self._log({"type": "decision", "stage": stage_num, "decision": decision})

            # Show reasoning immediately + save to context for resume
            reasoning = decision.get("reasoning", "")
            if reasoning:
                await self._notify(self.role_name, "progress", reasoning)
                self.context_doc += f"\n### Decision (stage {stage_num+1}): {reasoning[:200]}\n"
                self._save_progress()

            if action == "finish":
                if not self.stages:
                    # Force at least one stage
                    prompt = f"""{self._system_prompt}

GOAL: "{self.goal}"

You tried to finish without running any agents. You MUST launch at least one stage.
You are a manager — delegate the work to agents. Plan a stage now."""
                    await self._notify(self.role_name, "start", "Must run agents first, replanning...")
                    continue
                result.summary = decision.get("summary", "")
                await self._notify(self.role_name, "done",
                    f"**Goal achieved**\n\n{decision.get('reasoning', '')}\n\n{result.summary}")
                break

            elif action == "steer":
                stage_idx = decision.get("stage_index", len(self.stages) - 1)
                feedback = decision.get("feedback", "")
                await self._notify(self.role_name, "start",
                    f"Steering stage {stage_idx + 1}: {feedback[:100]}")

                if 0 <= stage_idx < len(self.stages):
                    old_stage = self.stages[stage_idx]
                    old_decision = copy.deepcopy(old_stage.get("decision", {}))
                    # Inject feedback into agent prompts
                    for ag in old_decision.get("agents", []):
                        ag["system_prompt"] = ag.get("system_prompt", "") + \
                            f"\n\nSUPERVISOR CORRECTION: {feedback}"

                    stage_result = await self._execute_stage(old_decision, stage_num)
                    self.stages.append({
                        "name": f"steer:{old_stage['name']}",
                        "phase": old_stage.get("phase", "unknown"),
                        "decision": old_decision,
                        "result_summary": stage_result.summary or "",
                        "responses": [r.content[:500] for r in stage_result.responses],
                    })
                    for resp in stage_result.responses:
                        result.add_response(resp)

                    stage_output = stage_result.summary or "\n".join(
                        f"[{r.agent_name}]: {r.content[:1000]}"
                        for r in stage_result.responses
                    )
                    prompt = self._build_next_prompt(stage_num, f"steer:{old_stage['name']}", stage_output)
                    await self._notify(self.role_name, "start", "Reviewing steered results...")
                else:
                    prompt = self._build_retry_prompt(decision)
                continue

            elif action == "retry":
                await self._notify(self.role_name, "start",
                    f"Retrying: {decision.get('feedback', '')}")
                prompt = self._build_retry_prompt(decision)
                continue

            elif action == "delegate":
                sub_goal = decision.get("sub_goal", "")
                max_sub = min(decision.get("max_sub_stages", 5), 5)
                await self._notify(self.role_name, "start",
                    f"**Delegating sub-goal**: {sub_goal[:200]}\n{decision.get('reasoning', '')}")

                # Spawn sub-supervisor (one level deeper)
                sub_model = decision.get("manager_model", "sonnet")
                sub_run = SupervisedRun(
                    goal=sub_goal,
                    on_update=self.on_update,
                    project_path=self.project_path,
                    supervisor_model=sub_model,
                    level=self.level + 1,
                )
                sub_run.max_stages = max_sub
                sub_run.context_doc = self.context_doc
                # Set parent relationship + add manager entry to our hierarchy
                sub_run.agent_hierarchy[sub_run.role_name]["parent"] = self.role_name
                if self.role_name in self.agent_hierarchy:
                    if sub_run.role_name not in self.agent_hierarchy[self.role_name]["children"]:
                        self.agent_hierarchy[self.role_name]["children"].append(sub_run.role_name)
                self.agent_hierarchy[sub_run.role_name] = {
                    "parent": self.role_name, "level": self.level + 1, "children": [],
                }
                sub_run._parent_hierarchy = copy.deepcopy({**self._parent_hierarchy, **self.agent_hierarchy})
                sub_result = await sub_run.run()

                # Merge sub-supervisor's hierarchy into ours
                for name, info in sub_run.agent_hierarchy.items():
                    if name not in self.agent_hierarchy:
                        self.agent_hierarchy[name] = info
                    elif name == sub_run.role_name:
                        # The sub-supervisor itself: update parent to us, merge children
                        self.agent_hierarchy[name]["parent"] = self.role_name
                        self.agent_hierarchy[name]["level"] = self.level + 1
                        for child in info.get("children", []):
                            if child not in self.agent_hierarchy[name]["children"]:
                                self.agent_hierarchy[name]["children"].append(child)
                # Ensure sub-supervisor is in our children list
                if sub_run.role_name not in self.agent_hierarchy.get(self.role_name, {}).get("children", []):
                    if self.role_name in self.agent_hierarchy:
                        self.agent_hierarchy[self.role_name]["children"].append(sub_run.role_name)
                # Emit updated hierarchy to frontend
                await self._notify(self.role_name, "hierarchy", json.dumps({**self._parent_hierarchy, **self.agent_hierarchy}))

                # Merge results
                for resp in sub_result.responses:
                    result.add_response(resp)
                # Update our context with sub-supervisor findings
                if sub_run.context_doc and sub_run.context_doc != self.context_doc:
                    self.context_doc = sub_run.context_doc

                self.stages.append({
                    "name": f"delegate:{sub_goal[:50]}",
                    "phase": "delegate",
                    "decision": decision,
                    "result_summary": sub_result.summary or "",
                    "responses": [r.content[:500] for r in sub_result.responses],
                })

                sub_output = sub_result.summary or "Sub-goal completed"
                prompt = self._build_next_prompt(stage_num, f"delegate:{sub_goal[:50]}", sub_output)
                await self._notify(self.role_name, "start", "Sub-goal completed, reviewing results...")
                continue

            elif action == "run_stage":
                stage_name = decision.get("stage_name", f"Stage {stage_num + 1}")
                phase = decision.get("phase", "unknown")
                self.current_phase = phase
                self.phase_history.append(phase)

                # Dynamic complexity: supervisor can adjust max_stages
                new_max = decision.get("max_stages")
                if new_max and isinstance(new_max, int) and 4 <= new_max <= 20:
                    self.max_stages = new_max

                # Include choices if supervisor provided them
                choices = decision.get("choices", [])
                choices_text = ""
                if choices and isinstance(choices, list) and len(choices) > 1:
                    choices_text = "\n\n[CHOICES:]\n" + "\n".join(f"{i+1}. {c}" for i, c in enumerate(choices))
                await self._notify(self.role_name, "done",
                    f"**Stage {stage_num + 1} [{phase.upper()}]: {stage_name}**\n{decision.get('reasoning', '')}{choices_text}")

                # Save checkpoint before execution (so stop mid-stage has state)
                self._save_progress()
                # Execute the stage (register as child task for cancellation)
                stage_coro = self._execute_stage(decision, stage_num)
                stage_task = asyncio.create_task(stage_coro)
                if self._job:
                    self._job._child_tasks.append(stage_task)
                try:
                    stage_result = await stage_task
                except asyncio.CancelledError:
                    await self._notify(self.role_name, "error", "Stage cancelled")
                    break
                finally:
                    # Clean up completed task to prevent memory leak
                    if self._job and stage_task in self._job._child_tasks:
                        self._job._child_tasks.remove(stage_task)

                # Save full results to files + track cost
                saved_files = self._save_stage_results(stage_num, stage_name, stage_result)
                stage_cost = sum(r.cost for r in stage_result.responses)
                self.total_cost += stage_cost

                # Update shared context document
                ctx_update = decision.get("context_update", "")
                if ctx_update:
                    self.context_doc += f"\n### {stage_name} ({phase}):\n{ctx_update}\n"
                # Compress context every 5 stages to prevent degradation
                if len(self.stages) > 0 and len(self.stages) % 5 == 0:
                    await self._compress_context()
                # Save progress to disk for recovery
                self._save_progress()

                self.stages.append({
                    "name": stage_name,
                    "phase": phase,
                    "decision": decision,
                    "result_summary": stage_result.summary or "",
                    "saved_files": saved_files,
                    "cost": stage_cost,
                })

                # Add responses to main result
                for resp in stage_result.responses:
                    result.add_response(resp)

                # Build prompt with full output + file paths + errors
                file_refs = "\n".join(f"  {f}" for f in saved_files) if saved_files else "  (none)"
                output_parts = []
                errors = []
                for r in stage_result.responses:
                    if r.is_error:
                        errors.append(f"[{r.agent_name}] ERROR: {r.error_message}")
                    else:
                        output_parts.append(f"[{r.agent_name}]: {r.content[:3000]}")
                stage_output = "\n".join(output_parts)
                if errors:
                    stage_output += "\n\nAGENT ERRORS:\n" + "\n".join(errors)
                if stage_result.summary:
                    stage_output = stage_result.summary + "\n\n" + stage_output
                stage_output += f"\n\nFull outputs saved to files:\n{file_refs}"
                # Detect agent requests for new team members
                agent_requests = []
                for r in stage_result.responses:
                    if not r.is_error and "[REQUEST_AGENT:" in r.content:
                        import re as _re
                        for m in _re.finditer(r'\[REQUEST_AGENT:\s*(.+?)\]', r.content):
                            agent_requests.append(f"{r.agent_name} requests: {m.group(1)}")
                if agent_requests:
                    stage_output += "\n\nAGENT REQUESTS FOR HELP:\n" + "\n".join(f"- {r}" for r in agent_requests)
                    stage_output += "\n\nIMPORTANT: Create the following requested agents in your next stage: " + "; ".join(agent_requests)
                prompt = self._build_next_prompt(stage_num, stage_name, stage_output)

                # Notify cost
                await self._notify(self.role_name, "progress",
                    f"Stage cost: ${stage_cost:.4f} | Total: ${self.total_cost:.4f}")
                await self._notify(self.role_name, "start", "Reviewing results, planning next stage...")

            elif action == "parallel_delegates":
                delegates = decision.get("delegates", [])
                if not delegates:
                    await self._notify(self.role_name, "error", "No delegates")
                    continue
                await self._notify(self.role_name, "done",
                    f"**Launching {len(delegates)} parallel Managers**\n{decision.get('reasoning', '')}")
                # Save checkpoint with decision before starting managers
                self.stages.append({"name": f"parallel_delegates ({len(delegates)})", "phase": "delegate", "decision": decision, "result_summary": ""})
                self._save_progress()

                # Pre-create all sub-supervisors and register them BEFORE starting
                sub_runs = []
                for d in delegates:
                    sub_model = d.get("manager_model", "sonnet")
                    sub_run = SupervisedRun(
                        goal=d["sub_goal"],
                        on_update=self.on_update,
                        project_path=self.project_path,
                        supervisor_model=sub_model,
                        level=self.level + 1,
                    )
                    sub_run.max_stages = min(d.get("max_sub_stages", 5), 5)
                    sub_run.context_doc = self.context_doc
                    sub_run.agent_hierarchy[sub_run.role_name]["parent"] = self.role_name
                    # Register ALL managers as children first
                    if self.role_name in self.agent_hierarchy:
                        if sub_run.role_name not in self.agent_hierarchy[self.role_name]["children"]:
                            self.agent_hierarchy[self.role_name]["children"].append(sub_run.role_name)
                    sub_runs.append(sub_run)

                # Add manager entries to our hierarchy so they exist before emitting
                for sub_run in sub_runs:
                    if sub_run.role_name not in self.agent_hierarchy:
                        self.agent_hierarchy[sub_run.role_name] = {
                            "parent": self.role_name,
                            "level": self.level + 1,
                            "children": [],
                        }
                # Emit hierarchy with all managers registered
                await self._notify(self.role_name, "hierarchy", json.dumps({**self._parent_hierarchy, **self.agent_hierarchy}))

                # Now pass complete parent hierarchy (with all siblings) to each
                full_parent = copy.deepcopy({**self._parent_hierarchy, **self.agent_hierarchy})
                for sub_run in sub_runs:
                    sub_run._parent_hierarchy = copy.deepcopy(full_parent)

                async def _run_sub(sr):
                    return sr, await sr.run()

                tasks = [asyncio.create_task(_run_sub(sr)) for sr in sub_runs]
                if self._job:
                    self._job._child_tasks.extend(tasks)

                combined_output = []
                for t in tasks:
                    try:
                        sub_run, sub_result = await t
                    except (asyncio.CancelledError, Exception) as e:
                        # Save partial progress even on cancel
                        self._save_progress()
                        continue
                    finally:
                        if self._job and t in self._job._child_tasks:
                            self._job._child_tasks.remove(t)
                    # Merge results
                    for resp in sub_result.responses:
                        result.add_response(resp)
                    self.total_cost += sub_run.total_cost
                    # Merge hierarchy
                    for name, info in sub_run.agent_hierarchy.items():
                        if name not in self.agent_hierarchy:
                            self.agent_hierarchy[name] = info
                    if sub_run.role_name not in self.agent_hierarchy.get(self.role_name, {}).get("children", []):
                        if self.role_name in self.agent_hierarchy:
                            self.agent_hierarchy[self.role_name]["children"].append(sub_run.role_name)
                    # Merge context
                    if sub_run.context_doc != self.context_doc:
                        self.context_doc = sub_run.context_doc
                    # Save checkpoint after each manager completes
                    self._save_progress()
                    self.stages.append({
                        "name": f"delegate:{sub_run.goal[:40]}",
                        "phase": "delegate",
                        "decision": {"sub_goal": sub_run.goal},
                        "result_summary": sub_result.summary or "",
                        "cost": sub_run.total_cost,
                    })
                    combined_output.append(f"### Manager: {sub_run.goal[:50]}\n{sub_result.summary or ''}")

                await self._notify(self.role_name, "hierarchy", json.dumps({**self._parent_hierarchy, **self.agent_hierarchy}))
                self._save_progress()
                prompt = self._build_next_prompt(stage_num, "parallel managers", "\n\n".join(combined_output))
                await self._notify(self.role_name, "start", "Reviewing manager results...")

            elif action == "run_parallel_stages":
                stages_data = decision.get("stages", [])
                if not stages_data:
                    await self._notify(self.role_name, "error", "No stages in run_parallel_stages")
                    continue
                choices = decision.get("choices", [])
                choices_text = ""
                if choices and isinstance(choices, list) and len(choices) > 1:
                    choices_text = "\n\n[CHOICES:]\n" + "\n".join(f"{i+1}. {c}" for i, c in enumerate(choices))
                await self._notify(self.role_name, "done",
                    f"**Running {len(stages_data)} stages in parallel**\n{decision.get('reasoning', '')}{choices_text}")

                # Run all stages concurrently
                async def _run_one(sd, sn):
                    sd.setdefault("action", "run_stage")
                    return await self._execute_stage(sd, sn)

                tasks_list = []
                for i, sd in enumerate(stages_data):
                    t = asyncio.create_task(_run_one(sd, stage_num + i))
                    if self._job:
                        self._job._child_tasks.append(t)
                    tasks_list.append((sd, t))

                all_saved = []
                combined_output = []
                for sd, t in tasks_list:
                    try:
                        sr = await t
                    except asyncio.CancelledError:
                        continue
                    finally:
                        if self._job and t in self._job._child_tasks:
                            self._job._child_tasks.remove(t)
                    sname = sd.get("stage_name", "parallel")
                    phase = sd.get("phase", "parallel")
                    self.phase_history.append(phase)
                    saved = self._save_stage_results(stage_num, sname, sr)
                    all_saved.extend(saved)
                    sc = sum(r.cost for r in sr.responses)
                    self.total_cost += sc
                    ctx = sd.get("context_update", "")
                    if ctx:
                        self.context_doc += f"\n### {sname} ({phase}):\n{ctx}\n"
                    self.stages.append({
                        "name": sname, "phase": phase, "decision": sd,
                        "result_summary": sr.summary or "", "saved_files": saved, "cost": sc,
                    })
                    for resp in sr.responses:
                        result.add_response(resp)
                    out = sr.summary or "\n".join(
                        f"[{r.agent_name}]: {r.content[:1000]}" for r in sr.responses
                    )
                    combined_output.append(f"### {sname}:\n{out}")

                self._save_progress()
                file_refs = "\n".join(f"  {f}" for f in all_saved)
                full_output = "\n\n".join(combined_output) + f"\n\nFull outputs saved:\n{file_refs}"
                prompt = self._build_next_prompt(stage_num, "parallel stages", full_output)
                await self._notify(self.role_name, "start", "Reviewing parallel results...")

            else:
                await self._notify(self.role_name, "error", f"Unknown action: {action}")
                break

        # Save final checkpoint + log
        self._save_progress()
        self._save_log()

        return result

    def _save_stage_results(self, stage_num: int, stage_name: str, stage_result) -> list[str]:
        """Save full agent outputs to files. Returns list of file paths."""
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in stage_name)[:50]
        stage_dir = self.run_dir / f"stage_{stage_num + 1}_{safe_name}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for resp in stage_result.responses:
            if resp.is_error or not resp.content:
                continue
            agent_safe = "".join(c if c.isalnum() or c in '-_' else '_' for c in resp.agent_name)[:40]
            fpath = stage_dir / f"{agent_safe}.md"
            fpath.write_text(
                f"# {resp.agent_name}\n"
                f"## Stage: {stage_name}\n"
                f"## Cost: ${resp.cost:.4f} | Duration: {resp.duration_ms}ms | Turns: {resp.num_turns}\n\n"
                f"{resp.content}",
                encoding="utf-8",
            )
            saved.append(str(fpath))
        # Also save summary if any
        if stage_result.summary:
            (stage_dir / "_summary.md").write_text(stage_result.summary, encoding="utf-8")
            saved.append(str(stage_dir / "_summary.md"))
        return saved

    async def _execute_stage(self, decision: dict, stage_num: int) -> OrchestraResult:
        """Execute a single stage using the coordinator."""
        from .coordinator import OrchestraCoordinator

        mode = decision.get("mode", "discuss")
        agents_data = decision.get("agents", [])
        options = decision.get("options", {})
        timeout = decision.get("timeout")  # optional per-stage timeout
        # Use refined stage_topic if provided, otherwise fall back to goal
        stage_topic = decision.get("stage_topic") or self.goal
        # Append shared context document if it exists
        if self.context_doc:
            stage_topic = f"{stage_topic}\n\n## Shared Context (findings from previous stages):\n{self.context_doc}"

        # Create agents in config (with lock to prevent parallel stage races)
        import yaml
        current_ids = {ag["id"] for ag in agents_data}
        async with _config_lock:
            raw = {}
            with open(CONFIG_PATH) as f:
                raw = yaml.safe_load(f) or {}
            if "agents" not in raw:
                raw["agents"] = {}

            # Clean up: remove agents not in current stage to prevent unbounded growth
            raw["agents"] = {k: v for k, v in raw["agents"].items() if k in current_ids}

            # Detect goal language for agent instructions
            lang_hint = f"\nIMPORTANT: Respond ONLY in the same language as: \"{self.goal[:50]}\""
            for ag in agents_data:
                raw["agents"][ag["id"]] = {
                    "display_name": ag.get("display_name", ag["id"]),
                    "model": ag.get("model", "sonnet"),
                    "system_prompt": ag.get("system_prompt", "") + lang_hint,
                    "allowed_tools": ag.get("allowed_tools", []),
                    "max_turns": ag.get("max_turns", 50),
                }
            with open(CONFIG_PATH, "w") as f:
                yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        # Record agents in hierarchy: parent=self.role_name, level=self.level+1
        for ag in agents_data:
            display = ag.get("display_name", ag["id"])
            if display not in self.agent_hierarchy:
                self.agent_hierarchy[display] = {
                    "parent": self.role_name,
                    "level": self.level + 1,
                    "children": [],
                }
                # Add as child of parent
                if self.role_name in self.agent_hierarchy:
                    parent_children = self.agent_hierarchy[self.role_name]["children"]
                    if display not in parent_children:
                        parent_children.append(display)

        # Emit hierarchy to frontend
        await self._notify(self.role_name, "hierarchy", json.dumps({**self._parent_hierarchy, **self.agent_hierarchy}))

        # Emit agent configs so they can be used for direct messaging
        agent_configs = {}
        for ag in agents_data:
            agent_configs[ag["id"]] = {
                "display_name": ag.get("display_name", ag["id"]),
                "model": ag.get("model", "sonnet"),
                "system_prompt": ag.get("system_prompt", ""),
                "allowed_tools": ag.get("allowed_tools", []),
                "max_turns": ag.get("max_turns", 50),
            }
        await self._notify(self.role_name, "agent_config", json.dumps(agent_configs))

        config = load_config(CONFIG_PATH)
        coordinator = OrchestraCoordinator(
            config=config,
            project_path=self.project_path,
        )

        agent_ids = [a["id"] for a in agents_data]

        # Dispatch to mode
        async def _dispatch():
            if mode == "discuss":
                return await coordinator.discuss(
                    topic=stage_topic, agent_names=agent_ids,
                    rounds=options.get("rounds", 2), on_update=self.on_update,
                )
            elif mode == "pipeline":
                steps = options.get("steps", [{"agent": a, "action": "process"} for a in agent_ids])
                parsed = []
                for s in steps:
                    if isinstance(s, dict):
                        parsed.append((s.get("agent", agent_ids[0] if agent_ids else ""), s.get("action", "process")))
                    elif isinstance(s, str):
                        parsed.append((agent_ids[0] if agent_ids else "", s))
                return await coordinator.pipeline(
                    topic=stage_topic, steps=parsed or [(a, "process") for a in agent_ids],
                    on_update=self.on_update,
                )
            elif mode == "parallel":
                tasks = options.get("tasks", [{"agent": a, "description": "work"} for a in agent_ids])
                parsed = []
                for t in tasks:
                    if isinstance(t, dict):
                        parsed.append((t.get("agent", agent_ids[0] if agent_ids else ""), t.get("description", "work")))
                    elif isinstance(t, str):
                        parsed.append((agent_ids[0] if agent_ids else "", t))
                return await coordinator.parallel(
                    topic=stage_topic, tasks=parsed or [(a, "work") for a in agent_ids],
                    on_update=self.on_update,
                )
            elif mode == "consensus":
                return await coordinator.consensus(
                    topic=stage_topic, agent_names=agent_ids, on_update=self.on_update,
                )
            elif mode == "custom":
                workflow = options.get("workflow", [])
                return await coordinator.custom(
                    topic=stage_topic, workflow=workflow, on_update=self.on_update,
                )
            else:
                return OrchestraResult(mode=mode, topic=self.goal)

        # Apply optional timeout
        if timeout and isinstance(timeout, (int, float)) and timeout > 0:
            try:
                stage_result = await asyncio.wait_for(_dispatch(), timeout=timeout)
            except asyncio.TimeoutError:
                if self.on_update:
                    r = self.on_update("Supervisor", "error", f"Stage timed out after {timeout}s")
                    if asyncio.iscoroutine(r): await r
                return OrchestraResult(mode=mode, topic=stage_topic)
        else:
            stage_result = await _dispatch()

        # BUG 1 fix: track summarizer/merge agents that aren't in the decision's agent list
        known_names = {ag.get("display_name", ag["id"]) for ag in agents_data}
        for resp in stage_result.responses:
            name = resp.agent_name
            if name and name not in self.agent_hierarchy and name not in known_names:
                self.agent_hierarchy[name] = {
                    "parent": self.role_name,
                    "level": self.level + 1,
                    "children": [],
                }
                if self.role_name in self.agent_hierarchy:
                    parent_children = self.agent_hierarchy[self.role_name]["children"]
                    if name not in parent_children:
                        parent_children.append(name)
        # Re-emit hierarchy if new agents were found
        if stage_result.responses:
            await self._notify(self.role_name, "hierarchy", json.dumps({**self._parent_hierarchy, **self.agent_hierarchy}))

        return stage_result

    def _build_next_prompt(self, stage_num: int, stage_name: str, output: str) -> str:
        history = "\n".join(
            f"Stage {i+1} [{s.get('phase', '?').upper()}] ({s['name']}): {s.get('result_summary', 'completed')[:200]}"
            for i, s in enumerate(self.stages)
        )
        phase_flow = " → ".join(self.phase_history) if self.phase_history else "none yet"
        used = len(self.stages)
        remaining = self.max_stages - used

        # Save full context to file instead of truncating
        context_section = ""
        if self.context_doc:
            ctx_file = self.run_dir / "context.md"
            ctx_file.write_text(self.context_doc, encoding="utf-8")
            # Include full context if small, file reference if large
            if len(self.context_doc) < 8000:
                context_section = f"\nSHARED CONTEXT:\n{self.context_doc}\n"
            else:
                context_section = f"\nSHARED CONTEXT (full doc at {ctx_file}, showing last 4000 chars):\n...{self.context_doc[-4000:]}\n"

        return f"""{self._system_prompt}

GOAL: "{self.goal}"

PHASE PROGRESSION: {phase_flow}
STAGES USED: {used} of {self.max_stages} ({remaining} remaining)
TOTAL COST: ${self.total_cost:.4f}
{context_section}
COMPLETED STAGES:
{history}

LATEST STAGE RESULTS ({stage_name}):
{output[:8000]}

Respond with a JSON object. What's next?"""

    def _build_retry_prompt(self, decision: dict) -> str:
        feedback = decision.get("feedback", "")
        phase_flow = " → ".join(self.phase_history) if self.phase_history else "none yet"
        used = len(self.stages)
        return f"""{self._system_prompt}

GOAL: "{self.goal}"

PHASE PROGRESSION: {phase_flow}
CURRENT PHASE: {self.current_phase}
STAGES USED: {used} of {self.max_stages}

PREVIOUS ATTEMPT FAILED. FEEDBACK: {feedback}

Modifications requested: {decision.get('modifications', 'none')}

Plan a corrected stage."""

    async def _compress_context(self):
        """Summarize context_doc to prevent unbounded growth."""
        if len(self.context_doc) < 3000:
            return  # small enough, no compression needed
        await self._notify(self.role_name, "start", "Compressing context document...")
        prompt = (
            f"Summarize the following findings into a concise document. "
            f"Keep ALL key facts, decisions, numbers, and action items. "
            f"Remove redundancy and verbose explanations. Same language as original.\n\n"
            f"{self.context_doc}"
        )
        try:
            compressed = await _call_supervisor(prompt, "haiku")
            if compressed and len(compressed) < len(self.context_doc):
                # Save full version to file before replacing
                archive = self.run_dir / f"context_full_stage_{len(self.stages)}.md"
                archive.write_text(self.context_doc, encoding="utf-8")
                self.context_doc = compressed
                await self._notify(self.role_name, "done",
                    f"Context compressed: {len(self.context_doc)} chars (full saved to {archive.name})")
        except Exception as e:
            await self._notify(self.role_name, "error", f"Context compression failed: {e}")

    def _save_progress(self):
        """Save progress to disk — both human-readable and machine-recoverable."""
        # Human-readable
        progress = self.run_dir / ".progress.md"
        progress.write_text(
            f"# Progress: {self.goal}\n\n"
            f"## Stages completed: {len(self.stages)}\n"
            f"## Total cost: ${self.total_cost:.4f}\n"
            f"## Phase history: {' → '.join(self.phase_history)}\n\n"
            f"## Context Document\n{self.context_doc}\n",
            encoding="utf-8",
        )
        # Machine-recoverable checkpoint
        checkpoint = {
            "goal": self.goal,
            "stages": list(self.stages),
            "context_doc": self.context_doc,
            "phase_history": self.phase_history,
            "current_phase": self.current_phase,
            "total_cost": self.total_cost,
            "max_stages": self.max_stages,
            "supervisor_model": self.supervisor_model,
            "level": self.level,
            "agent_hierarchy": self.agent_hierarchy,
        }
        (self.run_dir / ".checkpoint.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8",
        )

    def _save_log(self):
        """Save full execution log to disk."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_file = LOG_DIR / f"{ts}.json"
        log_data = {
            "goal": self.goal,
            "stages": self.stages,
            "log": self.log,
            "phase_history": self.phase_history,
            "context_doc": self.context_doc,
            "timestamp": ts,
        }
        log_file.write_text(json.dumps(log_data, indent=2, ensure_ascii=False))
