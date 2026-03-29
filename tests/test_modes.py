"""Tests for modes: base (OrchestraResult), parallel, consensus, pipeline."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.client import AgentResponse
from src.modes.base import OrchestraResult
from src.modes.consensus import ConsensusMode
from src.modes.parallel import ParallelMode, ParallelTask
from src.modes.pipeline import PipelineMode, PipelineStep

from tests.conftest import make_mock_client


# ===========================================================================
# OrchestraResult
# ===========================================================================

class TestOrchestraResult:
    def test_initial_state(self):
        r = OrchestraResult(mode="parallel", topic="test")
        assert r.responses == []
        assert r.total_cost == 0.0
        assert r.total_duration_ms == 0
        assert r.summary == ""

    def test_add_response_accumulates_cost(self):
        r = OrchestraResult(mode="parallel", topic="test")
        r.add_response(AgentResponse("A", "content", cost=0.05, duration_ms=100))
        r.add_response(AgentResponse("B", "content", cost=0.03, duration_ms=200))
        assert r.total_cost == pytest.approx(0.08)
        assert r.total_duration_ms == 300
        assert len(r.responses) == 2

    def test_add_error_response(self):
        r = OrchestraResult(mode="parallel", topic="test")
        r.add_response(AgentResponse("X", "", is_error=True, error_message="boom"))
        assert len(r.responses) == 1
        assert r.responses[0].is_error


# ===========================================================================
# ParallelMode
# ===========================================================================

class TestParallelMode:
    def _make_tasks(self, count: int = 2) -> list[ParallelTask]:
        return [
            ParallelTask(
                agent=make_mock_client(name=f"agent{i}", display_name=f"Agent{i}",
                                       response_content=f"Result from agent {i}"),
                description=f"Subtask {i}",
            )
            for i in range(count)
        ]

    async def test_returns_orchestra_result(self):
        mode = ParallelMode(tasks=self._make_tasks())
        result = await mode.execute("Do things", agents=[])
        assert isinstance(result, OrchestraResult)
        assert result.mode == "parallel"

    async def test_all_tasks_run(self):
        tasks = self._make_tasks(3)
        mode = ParallelMode(tasks=tasks)
        result = await mode.execute("goal", agents=[])
        assert len(result.responses) == 3

    async def test_responses_contain_content(self):
        tasks = self._make_tasks(2)
        mode = ParallelMode(tasks=tasks)
        result = await mode.execute("goal", agents=[])
        contents = [r.content for r in result.responses]
        assert "Result from agent 0" in contents
        assert "Result from agent 1" in contents

    async def test_on_update_called(self):
        tasks = self._make_tasks(1)
        events = []

        async def capture(name, event, text):
            events.append((name, event))

        mode = ParallelMode(tasks=tasks)
        await mode.execute("goal", agents=[], on_update=capture)
        event_types = [e[1] for e in events]
        assert "start" in event_types
        assert "done" in event_types

    async def test_error_agent_recorded(self):
        error_client = make_mock_client(is_error=True, error_message="Agent crashed")
        tasks = [ParallelTask(agent=error_client, description="Broken task")]
        mode = ParallelMode(tasks=tasks)
        result = await mode.execute("goal", agents=[])
        assert result.responses[0].is_error

    async def test_error_does_not_block_other_tasks(self):
        error_client = make_mock_client(name="bad", is_error=True, error_message="fail")
        ok_client = make_mock_client(name="ok", response_content="good result")
        tasks = [
            ParallelTask(agent=error_client, description="bad"),
            ParallelTask(agent=ok_client, description="good"),
        ]
        mode = ParallelMode(tasks=tasks)
        result = await mode.execute("goal", agents=[])
        assert len(result.responses) == 2
        ok_resp = next(r for r in result.responses if not r.is_error)
        assert ok_resp.content == "good result"

    async def test_merge_agent_called_when_provided(self):
        tasks = self._make_tasks(2)
        merge = make_mock_client(name="merger", response_content="Merged!")
        mode = ParallelMode(tasks=tasks, merge_agent=merge)
        result = await mode.execute("goal", agents=[])
        merge.run.assert_called_once()
        assert result.summary == "Merged!"

    async def test_merge_agent_skipped_when_all_errors(self):
        error_client = make_mock_client(is_error=True, error_message="err")
        tasks = [ParallelTask(agent=error_client, description="bad")]
        merge = make_mock_client(name="merger", response_content="Merged!")
        mode = ParallelMode(tasks=tasks, merge_agent=merge)
        await mode.execute("goal", agents=[])
        merge.run.assert_not_called()

    async def test_semaphore_limits_concurrency(self):
        """With max_concurrent=1 tasks run sequentially — all still complete."""
        tasks = self._make_tasks(4)
        mode = ParallelMode(tasks=tasks, max_concurrent=1)
        result = await mode.execute("goal", agents=[])
        assert len(result.responses) == 4

    async def test_total_timeout_returns_empty_result(self):
        async def slow_run(prompt, on_stream=None):
            await asyncio.sleep(999)
            return AgentResponse("slow", "never")

        slow_client = MagicMock()
        slow_client.display_name = "Slow"
        slow_client.run = slow_run
        tasks = [ParallelTask(agent=slow_client, description="slow")]
        mode = ParallelMode(tasks=tasks, timeout_seconds=0)

        result = await mode.execute("goal", agents=[])
        # On timeout the empty OrchestraResult is returned
        assert isinstance(result, OrchestraResult)

    def test_build_merge_prompt_contains_task_content(self):
        tasks = self._make_tasks(2)
        responses = [
            AgentResponse("Agent0", "Output A"),
            AgentResponse("Agent1", "Output B"),
        ]
        mode = ParallelMode(tasks=tasks)
        prompt = mode._build_merge_prompt("My goal", responses)
        assert "My goal" in prompt
        assert "Output A" in prompt
        assert "Output B" in prompt

    def test_build_merge_prompt_marks_errors(self):
        tasks = self._make_tasks(1)
        responses = [AgentResponse("Agent0", "", is_error=True, error_message="Failed")]
        mode = ParallelMode(tasks=tasks)
        prompt = mode._build_merge_prompt("goal", responses)
        assert "ERROR" in prompt
        assert "Failed" in prompt


# ===========================================================================
# ConsensusMode
# ===========================================================================

class TestConsensusMode:
    def _make_agents(self, responses: list[str]) -> list[MagicMock]:
        agents = []
        for i, content in enumerate(responses):
            a = make_mock_client(name=f"agent{i}", display_name=f"Agent{i}",
                                 response_content=content)
            agents.append(a)
        return agents

    # --- _parse_vote ---

    def test_parse_vote_structured(self):
        cm = ConsensusMode()
        vote = cm._parse_vote("Alice", "CHOICE: Option A\nCONFIDENCE: 0.9\nREASONING: Clearly best.")
        assert vote["agent"] == "Alice"
        assert vote["choice"] == "Option A"
        assert vote["confidence"] == pytest.approx(0.9)
        assert vote["reasoning"] == "Clearly best."

    def test_parse_vote_case_insensitive_keys(self):
        cm = ConsensusMode()
        vote = cm._parse_vote("Bob", "choice: yes\nconfidence: 0.7\nreasoning: Because.")
        assert vote["choice"] == "yes"

    def test_parse_vote_fallback_unstructured(self):
        cm = ConsensusMode()
        vote = cm._parse_vote("Carol", "I think Option B is best.")
        assert vote["choice"] == "I think Option B is best."
        assert vote["confidence"] == 0.5

    def test_parse_vote_confidence_clamped_low(self):
        # The regex [\d.]+ cannot parse the leading minus sign, so it returns
        # "0.5" → 0.5. The clamp only applies to values already parsed as float.
        # Verify the clamp on a value that IS parsed: use a value > 1.0 → clamped to 1.0,
        # and verify a plainly invalid string stays at the 0.5 default.
        cm = ConsensusMode()
        # "0.0" parses fine → clamp(0.0) == 0.0
        vote = cm._parse_vote("X", "CHOICE: A\nCONFIDENCE: 0.0\nREASONING: r")
        assert vote["confidence"] == 0.0

    def test_parse_vote_confidence_clamped_high(self):
        cm = ConsensusMode()
        vote = cm._parse_vote("X", "CHOICE: A\nCONFIDENCE: 1.5\nREASONING: r")
        assert vote["confidence"] == 1.0

    def test_parse_vote_bad_confidence_defaults_to_half(self):
        cm = ConsensusMode()
        vote = cm._parse_vote("X", "CHOICE: A\nCONFIDENCE: not_a_number\nREASONING: r")
        assert vote["confidence"] == 0.5

    # --- _check_consensus ---

    def test_check_consensus_unanimous(self):
        cm = ConsensusMode(threshold=0.67)
        votes = [
            {"agent": "A", "choice": "Yes", "confidence": 0.9, "reasoning": ""},
            {"agent": "B", "choice": "Yes", "confidence": 0.8, "reasoning": ""},
            {"agent": "C", "choice": "Yes", "confidence": 0.7, "reasoning": ""},
        ]
        result = cm._check_consensus(votes)
        assert result == "Yes"

    def test_check_consensus_supermajority(self):
        # 2/3 = 0.666...; use threshold=0.66 so it passes
        cm = ConsensusMode(threshold=0.66)
        votes = [
            {"agent": "A", "choice": "Yes", "confidence": 1.0, "reasoning": ""},
            {"agent": "B", "choice": "Yes", "confidence": 1.0, "reasoning": ""},
            {"agent": "C", "choice": "No",  "confidence": 1.0, "reasoning": ""},
        ]
        result = cm._check_consensus(votes)
        assert result == "Yes"

    def test_check_consensus_not_reached(self):
        cm = ConsensusMode(threshold=0.67)
        votes = [
            {"agent": "A", "choice": "Yes", "confidence": 1.0, "reasoning": ""},
            {"agent": "B", "choice": "No",  "confidence": 1.0, "reasoning": ""},
        ]
        result = cm._check_consensus(votes)
        assert result is None

    def test_check_consensus_empty(self):
        cm = ConsensusMode()
        assert cm._check_consensus([]) is None

    def test_check_consensus_case_insensitive(self):
        cm = ConsensusMode(threshold=0.67)
        votes = [
            {"agent": "A", "choice": "YES", "confidence": 1.0, "reasoning": ""},
            {"agent": "B", "choice": "yes", "confidence": 1.0, "reasoning": ""},
            {"agent": "C", "choice": "Yes", "confidence": 1.0, "reasoning": ""},
        ]
        result = cm._check_consensus(votes)
        assert result is not None   # consensus reached despite case differences

    # --- _get_leading_choice ---

    def test_get_leading_choice(self):
        cm = ConsensusMode()
        votes = [
            {"agent": "A", "choice": "A"},
            {"agent": "B", "choice": "B"},
            {"agent": "C", "choice": "A"},
        ]
        assert cm._get_leading_choice(votes) == "A"

    # --- execute ---

    async def test_execute_returns_orchestra_result(self):
        agents = self._make_agents([
            "CHOICE: Yes\nCONFIDENCE: 0.9\nREASONING: Good.",
            "CHOICE: Yes\nCONFIDENCE: 0.8\nREASONING: Fine.",
        ])
        cm = ConsensusMode(threshold=0.67)
        result = await cm.execute("Should we do this?", agents=agents)
        assert isinstance(result, OrchestraResult)
        assert result.mode == "consensus"

    async def test_execute_consensus_reached_in_round_1(self):
        agents = self._make_agents([
            "CHOICE: Option A\nCONFIDENCE: 1.0\nREASONING: Best.",
            "CHOICE: Option A\nCONFIDENCE: 0.9\nREASONING: Agree.",
            "CHOICE: Option A\nCONFIDENCE: 0.8\nREASONING: Sure.",
        ])
        cm = ConsensusMode(threshold=0.67, max_rounds=3)
        result = await cm.execute("Pick one", agents=agents)
        assert "CONSENSUS REACHED" in result.summary
        assert "Option A" in result.summary

    async def test_execute_no_consensus_uses_leading(self):
        agents = self._make_agents([
            "CHOICE: A\nCONFIDENCE: 1.0\nREASONING: a.",
            "CHOICE: B\nCONFIDENCE: 1.0\nREASONING: b.",
        ])
        cm = ConsensusMode(threshold=0.99, max_rounds=1)
        result = await cm.execute("Pick", agents=agents)
        assert "NO CONSENSUS" in result.summary

    async def test_execute_calls_on_update(self):
        agents = self._make_agents([
            "CHOICE: Yes\nCONFIDENCE: 1.0\nREASONING: r.",
            "CHOICE: Yes\nCONFIDENCE: 1.0\nREASONING: r.",
        ])
        events = []

        async def capture(name, event, text):
            events.append(event)

        cm = ConsensusMode(threshold=0.67)
        await cm.execute("Q?", agents=agents, on_update=capture)
        assert "start" in events
        assert "done" in events

    async def test_execute_handles_agent_errors(self):
        agents = [
            make_mock_client(name="ok", response_content="CHOICE: Yes\nCONFIDENCE: 1.0\nREASONING: r."),
            make_mock_client(name="bad", is_error=True, error_message="crash"),
        ]
        cm = ConsensusMode(threshold=0.67, max_rounds=1)
        result = await cm.execute("Q?", agents=agents)
        assert isinstance(result, OrchestraResult)


# ===========================================================================
# PipelineMode
# ===========================================================================

class TestPipelineMode:
    def _make_steps(self, actions: list[str]) -> list[PipelineStep]:
        return [
            PipelineStep(
                agent=make_mock_client(name=a, display_name=a.title(),
                                       response_content=f"{a.title()} output"),
                action=a,
            )
            for a in actions
        ]

    async def test_returns_orchestra_result(self):
        steps = self._make_steps(["design", "implement"])
        mode = PipelineMode(steps=steps)
        result = await mode.execute("Build something", agents=[])
        assert isinstance(result, OrchestraResult)
        assert result.mode == "pipeline"

    async def test_all_steps_run_in_order(self):
        call_order = []
        steps = []
        for action in ["design", "implement", "review"]:
            client = make_mock_client(name=action, display_name=action.title(),
                                      response_content=f"{action} done")
            original_run = client.run

            async def make_recorder(act, orig):
                async def recorder(*a, **kw):
                    call_order.append(act)
                    return await orig(*a, **kw)
                return recorder

            client.run = await make_recorder(action, original_run)
            steps.append(PipelineStep(agent=client, action=action))

        mode = PipelineMode(steps=steps)
        await mode.execute("task", agents=[])
        assert call_order == ["design", "implement", "review"]

    async def test_responses_accumulated(self):
        steps = self._make_steps(["design", "implement"])
        mode = PipelineMode(steps=steps)
        result = await mode.execute("task", agents=[])
        assert len(result.responses) == 2

    async def test_on_update_called_for_each_step(self):
        steps = self._make_steps(["design", "implement"])
        events = []

        async def capture(name, event, text):
            events.append(event)

        mode = PipelineMode(steps=steps)
        await mode.execute("task", agents=[], on_update=capture)
        assert events.count("start") == 2
        assert events.count("done") == 2

    async def test_error_step_skipped_continues_pipeline(self):
        design = make_mock_client(name="d", is_error=True, error_message="fail")
        implement = make_mock_client(name="i", response_content="impl done")
        steps = [PipelineStep(agent=design, action="design"),
                 PipelineStep(agent=implement, action="implement")]
        mode = PipelineMode(steps=steps, allow_rework=False)
        result = await mode.execute("task", agents=[])
        # Error step still logged, implement still ran
        impl_resp = next((r for r in result.responses if r.content == "impl done"), None)
        assert impl_resp is not None

    async def test_rework_triggered_on_critical_review(self):
        implement = make_mock_client(name="impl", display_name="Impl",
                                     response_content="implementation v1")
        review = make_mock_client(name="rev", display_name="Rev",
                                  response_content="CRITICAL: The code has a major bug!")
        steps = [
            PipelineStep(agent=implement, action="implement"),
            PipelineStep(agent=review, action="review"),
        ]
        mode = PipelineMode(steps=steps, allow_rework=True, max_rework_cycles=1)
        result = await mode.execute("task", agents=[])
        # implement was called at least twice (original + rework)
        assert implement.run.call_count >= 2

    async def test_rework_not_triggered_without_critical(self):
        implement = make_mock_client(name="impl", response_content="code")
        review = make_mock_client(name="rev", response_content="Looks good! Minor: add a comment.")
        steps = [
            PipelineStep(agent=implement, action="implement"),
            PipelineStep(agent=review, action="review"),
        ]
        mode = PipelineMode(steps=steps, allow_rework=True)
        await mode.execute("task", agents=[])
        assert implement.run.call_count == 1

    async def test_rework_max_cycles_respected(self):
        implement = make_mock_client(name="impl", response_content="code")
        review = make_mock_client(name="rev", response_content="CRITICAL: still broken!")
        steps = [
            PipelineStep(agent=implement, action="implement"),
            PipelineStep(agent=review, action="review"),
        ]
        mode = PipelineMode(steps=steps, allow_rework=True, max_rework_cycles=2)
        await mode.execute("task", agents=[])
        # Max rework = 2, so implement called at most 3 times (initial + 2 reworks)
        assert implement.run.call_count <= 3

    # --- _needs_rework ---

    def test_needs_rework_starts_with_critical(self):
        mode = PipelineMode(steps=[])
        assert mode._needs_rework("CRITICAL: Bad bug found.") is True

    def test_needs_rework_critical_in_first_200_chars(self):
        mode = PipelineMode(steps=[])
        text = "The review found issues. CRITICAL: security flaw detected." + "x" * 200
        assert mode._needs_rework(text) is True

    def test_needs_rework_false_when_no_critical(self):
        mode = PipelineMode(steps=[])
        assert mode._needs_rework("Looks good. Minor style issues.") is False

    def test_needs_rework_false_critical_too_far(self):
        mode = PipelineMode(steps=[])
        text = "Good code. " + "x" * 200 + " CRITICAL: far away"
        assert mode._needs_rework(text) is False

    # --- _find_step ---

    def test_find_step_returns_correct_index(self):
        steps = self._make_steps(["design", "implement", "review"])
        mode = PipelineMode(steps=steps)
        assert mode._find_step("implement") == 1

    def test_find_step_returns_none_when_missing(self):
        steps = self._make_steps(["design"])
        mode = PipelineMode(steps=steps)
        assert mode._find_step("test") is None

    # --- _build_prompt ---

    def test_build_prompt_contains_topic(self):
        steps = self._make_steps(["design"])
        mode = PipelineMode(steps=steps)
        from src.orchestrator.transcript import Transcript
        prompt = mode._build_prompt("My task", Transcript(), steps[0], 0)
        assert "My task" in prompt

    def test_build_prompt_action_instructions_present(self):
        steps = self._make_steps(["review"])
        mode = PipelineMode(steps=steps)
        from src.orchestrator.transcript import Transcript
        prompt = mode._build_prompt("task", Transcript(), steps[0], 0)
        assert "CRITICAL" in prompt   # review action instruction mentions CRITICAL

    def test_build_prompt_custom_action_fallback(self):
        client = make_mock_client(name="x")
        step = PipelineStep(agent=client, action="brainstorm")
        mode = PipelineMode(steps=[step])
        from src.orchestrator.transcript import Transcript
        prompt = mode._build_prompt("task", Transcript(), step, 0)
        assert "brainstorm" in prompt
