# Beeplex

**Chat with your Bee memories through MCP.**

Beeplex is the **senses and memory layer** for [Bee](https://bee.computer) — the wearable AI that continuously captures, transcribes, and extracts insights from your real-life conversations.

It is **not an agent**. It provides data, scoring, reports, voice editing, and disagreement analysis so that host agents (like [OpenCode](https://opencode.ai), Claude, Codex) can reason with rich, private, real-world context.

See [`docs/host-agents.md`](docs/host-agents.md) for the philosophy.

## Features

- **CLI** (`beeplex`): `status`, `now`, `search`, `conversations`, `todos`, `profile`, `report`, `diary`, `disagree`, `voice`, `ui`
- **MCP Server**: Native integration with MCP-compatible AI coding agents and tools
- **Web UI** + Voice Editor for transcripts
- **Independent analysis**: LLM scoring, temporal scoring, clinical extraction, disagreement detection between Bee summaries and local models
- **Reports**: Generate Office documents and interactive dashboards
- **Simulator**: Benchmarking and testing with recorded conversations (`simulator/`)
- **Skills for OpenCode**: Full `.agents/skills/bee-cli/` integration

Powered by and referencing [opencode](https://opencode.ai).

## Installation

```bash
cd beeplex
uv sync --extra reports   # includes Office report dependencies
# or
pip install -e ".[reports]"
# or (via requirements.txt)
pip install -r requirements.txt
```

Then verify:

```bash
uv run beeplex doctor
# or
beeplex doctor
```

**Authentication**: Run `beeplex doctor` (checks Bee CLI + reports extras). See [`.agents/skills/bee-cli/SKILL.md`](.agents/skills/bee-cli/SKILL.md) for Bee login.

## Quick Start

```bash
# Current context (always start here)
beeplex context

# Search memories
beeplex search "project deadline"

# Open web interface
beeplex ui

# Generate report + disagreement view + voice editor
beeplex report          # dashboard.html + Office reports
beeplex disagree        # disagreement.html
beeplex voice           # voice/*.html (slack.html + per-conversation editors)
beeplex --demo voice    # demo data version
```

For full Bee CLI commands and detailed usage, see [`.agents/skills/bee-cli/SKILL.md`](.agents/skills/bee-cli/SKILL.md).

`beeplex voice` creates self-contained HTML transcript editors (`family/voice/slack.html` + per-conversation pages) from Bee CLI data (or demo). `beeplex report` creates `dashboard.html` + Office files.

## Project Structure

- `python/` — Core CLI, MCP server, analysis modules (`client.py`, `server.py`, `reports.py`, `llm_scoring.py`, etc.)
- `tests/` — Comprehensive test suite
- `simulator/` — Benchmark harness and conversation replay
- `docs/` — Host agent guidelines
- `.agents/` — OpenCode skill definitions

Built to integrate seamlessly with **OpenCode** agents.

---

For more, explore the simulator (`simulator/bench.py`) or run the full test suite.
