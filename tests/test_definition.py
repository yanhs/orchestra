"""Tests for agents/definition.py — AgentRole, ModeConfig, OrchestraConfig, load_config."""

import textwrap
from pathlib import Path

import pytest
import yaml

from src.agents.definition import AgentRole, ModeConfig, OrchestraConfig, load_config


# ---------------------------------------------------------------------------
# AgentRole
# ---------------------------------------------------------------------------

class TestAgentRole:
    def test_defaults(self):
        role = AgentRole(
            name="dev",
            display_name="Developer",
            model="sonnet",
            system_prompt="You code.",
        )
        assert role.allowed_tools == []
        assert role.max_turns == 50

    def test_custom_fields(self):
        role = AgentRole(
            name="researcher",
            display_name="Researcher",
            model="opus",
            system_prompt="You research.",
            allowed_tools=["WebSearch", "Read"],
            max_turns=10,
        )
        assert role.name == "researcher"
        assert role.model == "opus"
        assert "WebSearch" in role.allowed_tools
        assert role.max_turns == 10


# ---------------------------------------------------------------------------
# ModeConfig
# ---------------------------------------------------------------------------

class TestModeConfig:
    def test_max_rounds_default(self):
        mc = ModeConfig(name="discuss")
        assert mc.max_rounds == 2

    def test_max_rounds_custom(self):
        mc = ModeConfig(name="discuss", settings={"max_rounds": 5})
        assert mc.max_rounds == 5

    def test_default_agents_empty(self):
        mc = ModeConfig(name="discuss")
        assert mc.default_agents == []

    def test_default_agents_set(self):
        mc = ModeConfig(name="discuss", settings={"default_agents": ["alpha", "beta"]})
        assert mc.default_agents == ["alpha", "beta"]

    def test_summarizer_none(self):
        mc = ModeConfig(name="discuss")
        assert mc.summarizer is None

    def test_summarizer_set(self):
        mc = ModeConfig(name="discuss", settings={"summarizer": "editor"})
        assert mc.summarizer == "editor"


# ---------------------------------------------------------------------------
# OrchestraConfig
# ---------------------------------------------------------------------------

class TestOrchestraConfig:
    def _make_config(self):
        agents = {
            "alice": AgentRole("alice", "Alice", "sonnet", "Prompt A"),
            "bob": AgentRole("bob", "Bob", "haiku", "Prompt B"),
        }
        modes = {
            "discuss": ModeConfig("discuss", {"max_rounds": 3}),
        }
        return OrchestraConfig(agents=agents, modes=modes)

    def test_get_agent_success(self):
        cfg = self._make_config()
        role = cfg.get_agent("alice")
        assert role.display_name == "Alice"

    def test_get_agent_missing_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError, match="Unknown agent 'charlie'"):
            cfg.get_agent("charlie")

    def test_get_agent_error_lists_available(self):
        cfg = self._make_config()
        with pytest.raises(ValueError, match="alice"):
            cfg.get_agent("nobody")

    def test_get_mode_success(self):
        cfg = self._make_config()
        mode = cfg.get_mode("discuss")
        assert mode.max_rounds == 3

    def test_get_mode_missing_raises(self):
        cfg = self._make_config()
        with pytest.raises(ValueError, match="Unknown mode 'pipeline'"):
            cfg.get_mode("pipeline")


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def _write_yaml(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "agents.yaml"
        p.write_text(textwrap.dedent(content))
        return p

    def test_loads_agents(self, tmp_path):
        cfg_file = self._write_yaml(tmp_path, """
            agents:
              dev:
                display_name: Developer
                model: sonnet
                system_prompt: "Write code."
                allowed_tools: [Read, Write]
                max_turns: 20
            modes: {}
        """)
        cfg = load_config(cfg_file)
        assert "dev" in cfg.agents
        role = cfg.agents["dev"]
        assert role.display_name == "Developer"
        assert role.model == "sonnet"
        assert role.allowed_tools == ["Read", "Write"]
        assert role.max_turns == 20

    def test_agent_defaults(self, tmp_path):
        cfg_file = self._write_yaml(tmp_path, """
            agents:
              minimal:
                system_prompt: "Be brief."
            modes: {}
        """)
        cfg = load_config(cfg_file)
        role = cfg.agents["minimal"]
        assert role.display_name == "Minimal"   # title-cased from key
        assert role.model == "sonnet"            # default
        assert role.allowed_tools == []
        assert role.max_turns == 50

    def test_loads_modes(self, tmp_path):
        cfg_file = self._write_yaml(tmp_path, """
            agents: {}
            modes:
              discuss:
                max_rounds: 4
                default_agents: [alpha, beta]
                summarizer: gamma
        """)
        cfg = load_config(cfg_file)
        assert "discuss" in cfg.modes
        mode = cfg.modes["discuss"]
        assert mode.max_rounds == 4
        assert mode.default_agents == ["alpha", "beta"]
        assert mode.summarizer == "gamma"

    def test_empty_yaml(self, tmp_path):
        cfg_file = self._write_yaml(tmp_path, "agents: {}\nmodes: {}\n")
        cfg = load_config(cfg_file)
        assert cfg.agents == {}
        assert cfg.modes == {}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_multiple_agents(self, tmp_path):
        cfg_file = self._write_yaml(tmp_path, """
            agents:
              alpha:
                display_name: Alpha
                model: opus
                system_prompt: "Alpha prompt"
              beta:
                display_name: Beta
                model: haiku
                system_prompt: "Beta prompt"
            modes: {}
        """)
        cfg = load_config(cfg_file)
        assert len(cfg.agents) == 2
        assert cfg.agents["alpha"].model == "opus"
        assert cfg.agents["beta"].model == "haiku"
