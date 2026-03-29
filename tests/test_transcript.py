"""Tests for orchestrator/transcript.py — Transcript and TranscriptEntry."""

import pytest

from src.orchestrator.transcript import Transcript, TranscriptEntry


class TestTranscriptEntry:
    def test_fields(self):
        e = TranscriptEntry(agent_name="Alice", content="Hello", round_num=2)
        assert e.agent_name == "Alice"
        assert e.content == "Hello"
        assert e.round_num == 2

    def test_default_round(self):
        e = TranscriptEntry(agent_name="Bob", content="Hi")
        assert e.round_num == 0


class TestTranscript:
    def test_empty_format(self):
        t = Transcript()
        assert t.format() == ""

    def test_add_single_entry(self):
        t = Transcript()
        t.add("Alice", "My response")
        assert len(t.entries) == 1
        assert t.entries[0].agent_name == "Alice"
        assert t.entries[0].content == "My response"
        assert t.entries[0].round_num == 1

    def test_entries_start_at_round_1(self):
        t = Transcript()
        t.add("Alice", "Hello")
        assert t.entries[0].round_num == 1

    def test_next_round_increments(self):
        t = Transcript()
        t.add("Alice", "Round 1")
        t.next_round()
        t.add("Bob", "Round 2")
        assert t.entries[0].round_num == 1
        assert t.entries[1].round_num == 2

    def test_format_single_round_full(self):
        t = Transcript()
        t.add("Alice", "Hello there")
        t.add("Bob", "Hi back")
        result = t.format()
        assert "**[Alice]:**" in result
        assert "Hello there" in result
        assert "**[Bob]:**" in result
        assert "Hi back" in result

    def test_format_no_round_header_for_round_1(self):
        t = Transcript()
        t.add("Alice", "content")
        result = t.format()
        assert "--- Round 1 ---" not in result

    def test_format_round_header_for_round_2_plus(self):
        t = Transcript()
        t.add("Alice", "Round 1 content")
        t.next_round()
        t.add("Bob", "Round 2 content")
        result = t.format()
        assert "--- Round 2 ---" in result

    def test_format_truncates_early_rounds(self):
        """Rounds below cutoff should be truncated to 300 chars."""
        t = Transcript()
        long_content = "X" * 500
        t.add("Alice", long_content)        # round 1
        t.next_round()
        t.add("Bob", "Round 2")             # round 2
        t.next_round()
        t.add("Carol", "Round 3")           # round 3
        # max_full_rounds=2 → cutoff = max(1, 3-2+1) = 2 → round 1 is truncated
        result = t.format(max_full_rounds=2)
        assert "(summary)" in result
        assert "..." in result
        # Round 2+ are shown in full
        assert "**[Bob]:**" in result
        assert "**[Carol]:**" in result

    def test_format_short_content_not_truncated(self):
        """Content ≤300 chars in early rounds should NOT get ellipsis."""
        t = Transcript()
        short = "Short message"
        t.add("Alice", short)        # round 1
        t.next_round()
        t.add("Bob", "R2")           # round 2
        t.next_round()
        t.add("Carol", "R3")         # round 3
        result = t.format(max_full_rounds=2)
        assert "..." not in result
        assert "Short message" in result

    def test_format_max_full_rounds_1(self):
        """With max_full_rounds=1 only the last round is in full."""
        t = Transcript()
        t.add("Alice", "R1 " * 200)   # > 300 chars
        t.next_round()
        t.add("Bob", "R2 content")
        result = t.format(max_full_rounds=1)
        assert "(summary)" in result
        assert "**[Bob]:**" in result

    def test_multiple_agents_same_round(self):
        t = Transcript()
        t.add("Alice", "Alice says")
        t.add("Bob", "Bob says")
        t.add("Carol", "Carol says")
        result = t.format()
        assert "Alice says" in result
        assert "Bob says" in result
        assert "Carol says" in result

    def test_entries_accumulate_across_rounds(self):
        t = Transcript()
        t.add("A", "msg1")
        t.next_round()
        t.add("B", "msg2")
        t.next_round()
        t.add("C", "msg3")
        assert len(t.entries) == 3
        assert [e.round_num for e in t.entries] == [1, 2, 3]
