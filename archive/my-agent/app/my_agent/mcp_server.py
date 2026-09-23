#!/usr/bin/env python3
"""beeplex MCP server (stdio).

Exposes the beeplex copilot tools over the Model Context Protocol, the same
way ``bee mcp serve`` exposes the Bee CLI: any MCP-aware client (Claude Code,
Claude Desktop, Cursor, ...) can call beeplex tools directly.

Run:
    /path/to/my-agent/.venv/bin/python /path/to/my-agent/app/my_agent/mcp_server.py

Works from any cwd: it bootstraps ``app/`` onto sys.path itself, and the
tools resolve the beeplex checkout relative to this file (override with
BEEPLEX_DIR).

Claude Code:
    claude mcp add beeplex -- /abs/path/to/my-agent/.venv/bin/python \\
        /abs/path/to/my-agent/app/my_agent/mcp_server.py

Claude Desktop (claude_desktop_config.json):
    { "mcpServers": { "beeplex": {
        "command": "/abs/path/to/my-agent/.venv/bin/python",
        "args": ["/abs/path/to/my-agent/app/my_agent/mcp_server.py"],
        "env": { "BEEX_MOCK": "1" }
    } } }

Set BEEX_MOCK=1 to run against clearly-labelled demo data instead of the
live Bee CLI (useful for testing without a Bee login).

Tool implementations live in my_agent/tools.py, shared with the strands
agent in main.py. To add a tool: implement ``<name>_impl`` there, then
register it below.
"""

import sys
from pathlib import Path

# Make `my_agent` importable no matter where this script is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from my_agent.tools import (  # noqa: E402
    bee_diary_impl,
    fetch_conversations_impl,
    generate_report_impl,
    score_conversations_impl,
    user_profile_impl,
)

server = MCPServer(
    "beeplex",
    instructions=(
        "Copilot tools for the beeplex project: the user's Bee wearable "
        "conversations, scored for engagement (heat) and forward motion "
        "(whether the heat cooks anything), with Word/Excel/PowerPoint "
        "reports, a coaching dashboard, and Bee's first-person diary. "
        "If a tool reports mock mode, say so plainly: the Bee CLI isn't "
        "connected, so the data is clearly-labelled demo data, not the "
        "user's real conversations. Never paste transcript contents into "
        "chat; summaries, scores, and file names only."
    ),
)


@server.tool()
def fetch_conversations(limit: int = 5) -> str:
    """Fetch the most recent Bee conversations.

    One line per conversation: recording date, session title, key topic.
    Also reports whether the data is live (Bee CLI) or mock fallback.
    """
    return fetch_conversations_impl(limit=limit)


@server.tool()
def score_conversations(limit: int = 5) -> str:
    """Score the most recent Bee conversations for engagement and forward motion.

    Runs beeplex's full scoring pipeline (deterministic + temporal signals,
    plus the LLM layer when a key is configured) and reports each
    conversation's engagement level, forward motion, and tone.
    """
    return score_conversations_impl(limit=limit)


@server.tool()
def generate_report(limit: int = 10) -> str:
    """Generate the beeplex Word/Excel/PowerPoint reports into family/.

    Fetches the latest conversations, scores them, and writes the transcript
    log (.docx), metrics spreadsheet (.xlsx), and insights deck (.pptx), plus
    regenerates the coaching dashboard (family/dashboard.html). Can take a
    few minutes; the result lists the files written.
    """
    return generate_report_impl(limit=limit)


@server.tool()
def bee_diary(limit: int = 3) -> str:
    """Read Bee's diary entry for today, in Bee's own first-person voice.

    Derives who Bee has become from your history (maturity, temperament, what
    it notices, what it remembers) and writes tonight's diary entry to
    family/Bee_YYYY-MM-DD.md.
    """
    return bee_diary_impl(limit=limit)


@server.tool()
def user_profile(full: bool = False, limit: int = 50) -> str:
    """Build/update the user's living profile and return it.

    Incrementally folds new Bee conversations into family/user.md (people,
    projects, preferences, events) and returns the profile text. Pass
    full=True to rebuild from scratch instead of incrementally.
    """
    return user_profile_impl(full=full, limit=limit)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
