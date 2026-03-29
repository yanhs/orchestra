"""Tests for orchestrator/sessions.py — session persistence."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import src.orchestrator.sessions as sessions_module
from src.orchestrator.sessions import get_session, load_sessions, save_sessions, set_session


class TestLoadSessions:
    def test_returns_empty_dict_when_file_missing(self, tmp_path):
        fake_path = tmp_path / "sessions.json"
        with patch.object(sessions_module, "SESSIONS_FILE", fake_path):
            result = load_sessions()
        assert result == {}

    def test_loads_existing_file(self, tmp_path):
        fake_path = tmp_path / "sessions.json"
        fake_path.write_text(json.dumps({"agent_a": "sess_001", "agent_b": "sess_002"}))
        with patch.object(sessions_module, "SESSIONS_FILE", fake_path):
            result = load_sessions()
        assert result == {"agent_a": "sess_001", "agent_b": "sess_002"}

    def test_returns_empty_on_corrupt_json(self, tmp_path):
        fake_path = tmp_path / "sessions.json"
        fake_path.write_text("{ invalid json")
        with patch.object(sessions_module, "SESSIONS_FILE", fake_path):
            result = load_sessions()
        assert result == {}


class TestSaveSessions:
    def test_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "sub" / "dir" / "sessions.json"
        with patch.object(sessions_module, "SESSIONS_FILE", nested):
            save_sessions({"x": "y"})
        assert nested.exists()

    def test_writes_json(self, tmp_path):
        fake_path = tmp_path / "sessions.json"
        with patch.object(sessions_module, "SESSIONS_FILE", fake_path):
            save_sessions({"dev": "abc123"})
        data = json.loads(fake_path.read_text())
        assert data == {"dev": "abc123"}

    def test_overwrites_existing(self, tmp_path):
        fake_path = tmp_path / "sessions.json"
        fake_path.write_text(json.dumps({"old": "value"}))
        with patch.object(sessions_module, "SESSIONS_FILE", fake_path):
            save_sessions({"new": "value"})
        data = json.loads(fake_path.read_text())
        assert "old" not in data
        assert data["new"] == "value"


class TestGetSetSession:
    def test_get_missing_agent_returns_none(self, tmp_path):
        fake_path = tmp_path / "sessions.json"
        with patch.object(sessions_module, "SESSIONS_FILE", fake_path):
            result = get_session("nonexistent_agent")
        assert result is None

    def test_set_and_get_roundtrip(self, tmp_path):
        fake_path = tmp_path / "sessions.json"
        with patch.object(sessions_module, "SESSIONS_FILE", fake_path):
            set_session("dev", "session_xyz")
            result = get_session("dev")
        assert result == "session_xyz"

    def test_set_does_not_clobber_other_agents(self, tmp_path):
        fake_path = tmp_path / "sessions.json"
        with patch.object(sessions_module, "SESSIONS_FILE", fake_path):
            set_session("alice", "sess_alice")
            set_session("bob", "sess_bob")
            assert get_session("alice") == "sess_alice"
            assert get_session("bob") == "sess_bob"

    def test_set_overwrites_existing_session(self, tmp_path):
        fake_path = tmp_path / "sessions.json"
        with patch.object(sessions_module, "SESSIONS_FILE", fake_path):
            set_session("dev", "old_session")
            set_session("dev", "new_session")
            assert get_session("dev") == "new_session"
