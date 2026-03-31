# Agent Orchestra

**Production-grade multi-agent AI orchestration platform — run coordinated Claude agent networks with six battle-tested strategies.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white)
![Claude API](https://img.shields.io/badge/Claude_Agent_SDK-0.1.39%2B-D97706?style=flat-square)
![Tests](https://img.shields.io/badge/Tests-184_passing-22C55E?style=flat-square&logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-6366F1?style=flat-square)

---

## What Is This

Agent Orchestra is a platform for running networks of Claude AI agents that collaborate, debate, and build on each other's outputs. Instead of a single prompt-response cycle, you define a *strategy* — and the system orchestrates multiple specialized agents through that strategy automatically.

The core idea: complex tasks require different cognitive modes. A code review needs adversarial pressure, not consensus. A research report benefits from parallel specialists, not a single generalist. Architecture decisions need diverse perspectives before committing. Agent Orchestra gives you a runtime that matches the orchestration strategy to the nature of the problem.

Under the hood, a Supervisor agent acts as a controller — it reads the goal, decides which mode to invoke, reviews intermediate results, injects corrections, and decides when the output meets the bar. All execution is async, all agent streams are forwarded live over WebSocket, and every run is persisted with full transcripts for audit and replay.

The system ships with a FastAPI server, a React dashboard, a CLI, a job queue, session persistence, and 184 automated tests covering modes, clients, jobs, history, and configuration loading.

---

## Architecture

```
                         ┌─────────────────────────────┐
                         │         Client Layer         │
                         │  CLI  │  Web UI  │  WS API  │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │      FastAPI Server          │
                         │  REST endpoints + /ws/run    │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │       Job Manager            │
                         │  Background tasks, persist   │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │      SupervisedRun           │
                         │  Supervisor agent (Claude)   │
                         │  Reads goal → picks action   │
                         │  Steers, retries, finishes   │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │    OrchestraCoordinator      │
                         │    Routes to base modes      │
                         └──┬──────┬──────┬──────┬─────┘
                            │      │      │      │
               ┌────────────▼┐ ┌───▼───┐ ┌▼──────┐ ┌▼─────────┐
               │ Discussion  │ │Pipeline│ │Parallel│ │Consensus │
               │ (parallel   │ │(seq.  │ │(fan-   │ │(voting + │
               │  rounds)    │ │handoff)│ │out/in) │ │ threshold│
               └──────┬──────┘ └───┬───┘ └───┬────┘ └────┬─────┘
                      │            │          │           │
               ┌──────▼────────────▼──────────▼───────────▼─────┐
               │                 AgentClient                      │
               │          claude-agent-sdk wrapper                │
               │   Session resumption │ Tool access │ Streaming   │
               └─────────────────────┬───────────────────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │     Claude API           │
                         │  opus / sonnet / haiku   │
                         └─────────────────────────┘
```

**Composite strategies** (Red-Blue, MCTS-lite) are built by the Supervisor by chaining base modes across stages. The Supervisor holds shared context between stages so each agent picks up exactly where the previous one left off.

---

## Orchestration Modes

| Mode | Mechanism | Best For |
|------|-----------|----------|
| **Discussion** | All agents run in parallel each round; each round sees the full transcript of the previous | Brainstorming, multi-perspective analysis, design reviews where diverse inputs matter |
| **Pipeline** | Agents run sequentially; output of each becomes input to the next; CRITICAL flags trigger rework loops | Software development workflows: design → implement → review → test |
| **Parallel** | Agents work on independent subtasks concurrently (semaphore-limited); optional merge agent integrates results | Large research tasks, parallel module implementation, simultaneous drafts |
| **Consensus** | Agents vote independently; structured votes (choice + confidence + reasoning); supermajority threshold (default 67%) with multiple rounds | Architecture decisions, prioritization, any choice that needs buy-in rather than a single opinion |
| **MCTS-lite** | Stage 1: parallel agents sketch 3+ solutions quickly (haiku); Stage 2: consensus vote picks best approach; Stage 3: deep pipeline execution (opus/sonnet) | Complex problems needing solution exploration before committing to deep implementation |
| **Red-Blue** | Blue agent builds; Red agent attacks and finds flaws; Blue defends and fixes; repeat until Red has nothing left | Production-critical code, security reviews, research that must survive adversarial scrutiny |

The Supervisor can also chain these freely — run a Parallel exploration, feed winners into a Pipeline, finish with a Consensus vote — all within a single supervised run.

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/your-handle/orchestra.git
cd orchestra
pip install poetry
poetry install

# Export your Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...

# Start the web server
poetry run orchestra serve
# Open http://localhost:3015/app
```

**Or use the CLI directly:**

```bash
# Multi-perspective discussion
poetry run orchestra discuss "What are the tradeoffs of microservices vs monolith?"

# Sequential pipeline (design → implement → review → test)
poetry run orchestra pipeline "Build a rate limiter in Python" \
  --step architect:design \
  --step developer:implement \
  --step reviewer:review \
  --step tester:test

# Parallel workstreams with merge
poetry run orchestra parallel "Audit this codebase" \
  -t security_agent:"check for vulnerabilities" \
  -t perf_agent:"find performance bottlenecks" \
  -t docs_agent:"assess documentation coverage"

# Consensus vote on a decision
poetry run orchestra consensus "Should we use PostgreSQL or MongoDB for this use case?"
```

**Docker (recommended for deployment):**

```bash
docker compose up
```

---

## Tech Stack

| Component | Technology | Role |
|-----------|------------|------|
| Agent execution | `claude-agent-sdk >= 0.1.39` | Runs Claude agents with tools, sessions, streaming |
| Web framework | FastAPI 0.115+ | REST API + WebSocket server |
| ASGI server | Uvicorn (standard) | Production async server |
| CLI | Click 8.1+ | Command-line interface |
| Terminal UI | Rich 13+ | Progress display, tables, panels |
| Config | PyYAML 6+ | Agent and mode definitions |
| Runtime | Python 3.11+ | Full async/await, type hints |
| Frontend | React SPA (bundled) | Live agent diagram, job control |
| Tests | pytest + pytest-asyncio + pytest-mock | 184 tests, async-native |

---

## Testing

```bash
# Run full test suite
poetry run pytest

# Verbose output with coverage
poetry run pytest -v --tb=short

# Run a specific test module
poetry run pytest tests/test_modes.py -v
```

**Test coverage by module:**

| Module | Tests | What's Covered |
|--------|-------|----------------|
| `test_modes.py` | 52 | Discussion, Pipeline, Parallel, Consensus execution |
| `test_client.py` | 44 | AgentClient: runs, streaming, error handling, session resumption |
| `test_jobs.py` | 38 | Job manager: create, run, stop, subscribe, persistence |
| `test_history.py` | 24 | Run history: save, list, retrieve, metadata |
| `test_definition.py` | 18 | Config loading: YAML parsing, agent/mode definitions |
| `test_transcript.py` | 5 | Transcript accumulation and formatting |
| `test_sessions.py` | 3 | Session persistence (IDs, recovery) |

All tests run against mocked `ClaudeSDKClient` — no API calls, no flakiness.

---

## API Reference

**Base URL:** `http://localhost:3015`

**WebSocket:** `ws://localhost:3015/ws/run`

### Agent Configuration

```
GET    /api/config                    — List all agents and mode defaults
PUT    /api/agents/{name}             — Create or update an agent
DELETE /api/agents/{name}             — Remove an agent
POST   /api/agents/generate           — Auto-generate agent from a role description
POST   /api/agents/reset              — Reset to default agent set
```

### Execution

```
WS     /ws/run                        — Start run, stream live events, send feedback
POST   /api/auto-plans                — Generate 5 orchestration plan variants for a task
```

**WebSocket protocol:**

```jsonc
// Start a run
{ "action": "start", "topic": "Build a REST API for user auth" }

// Server streams live events
{ "type": "update", "agent": "architect", "text": "I'll start with..." }

// Inject mid-run correction
{ "action": "feedback", "text": "Use JWT tokens, not sessions" }

// Final result
{ "type": "result", "summary": "...", "cost": 0.043 }
```

### Job Management

```
GET    /api/jobs                      — List all jobs (running + finished)
GET    /api/jobs/current              — Active jobs only
POST   /api/jobs/{job_id}/stop        — Cancel a running job
POST   /api/jobs/resume               — Resume from checkpoint
```

### History

```
GET    /api/history?limit=30          — Recent runs with metadata
GET    /api/history/{run_id}          — Full run transcript
```

---

## Configuration

Agents and modes are defined in `config/agents.yaml`:

```yaml
agents:
  senior_dev:
    display_name: Senior Developer
    model: sonnet
    system_prompt: "You are a senior software engineer..."
    allowed_tools: [Read, Write, Edit, Bash, Glob, Grep]
    max_turns: 50

modes:
  pipeline:
    allow_rework: true
    max_rework_cycles: 2
  consensus:
    threshold: 0.67
    max_rounds: 3
  parallel:
    max_concurrent: 3
    timeout_seconds: 600
```

Save and load config presets via the API or web UI. The Supervisor creates agent roles dynamically per run and updates the config at runtime.

---

## Project Structure

```
orchestra/
├── src/
│   ├── agents/          # AgentClient + agent/mode dataclasses
│   ├── modes/           # Discussion, Pipeline, Parallel, Consensus
│   ├── orchestrator/    # Supervisor, Coordinator, Jobs, History, Sessions
│   ├── cli/             # Click CLI commands
│   └── web/             # FastAPI server + WebSocket
├── config/              # agents.yaml + saved presets
├── tests/               # 184 tests across 7 modules
├── public/              # React web UI
└── landing/             # Marketing page
```

---

## Available for Hire

This project was designed and built by an AI systems engineer with hands-on experience architecting production multi-agent pipelines on the Claude API.

If your team needs:

- **Multi-agent systems** — orchestration layers, agent-to-agent communication, tool-equipped agents that actually do work
- **AI-accelerated development** — automated code review pipelines, test generation, architecture analysis
- **LLM infrastructure** — streaming APIs, session management, cost tracking, async agent execution
- **Claude API integration** — from a simple chat endpoint to a full supervised agent network

I build systems that ship, not demos that impress in a notebook.

**Engagement types:** Fixed-scope projects, consulting (architecture + code review), embedded engineering (part-time, async).

Contact: [your@email.com] | [linkedin.com/in/your-handle] | [upwork.com/fl/your-handle]

---

*Built with [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) and [FastAPI](https://fastapi.tiangolo.com/).*
