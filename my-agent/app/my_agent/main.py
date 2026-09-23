"""my-agent: a copilot for the beeplex folder.

Instead of the 00-getting-started sample's customer-support tools, this agent's
tools drive the user's Bee hackathon project (beeplex): fetching today's Bee
conversations, scoring them, generating the Word/Excel/PowerPoint reports,
and reading Bee's diary (the persona mode).

Wrapped in BedrockAgentCoreApp so it runs both locally (agentcore dev) and on
AgentCore Runtime (agentcore deploy). The model is loaded from model/load.py,
which defaults to ca.amazon.nova-micro-v1:0 in ca-central-1.
"""

import os
import subprocess
import sys
from pathlib import Path

from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from model.load import load_model

app = BedrockAgentCoreApp()

log = app.logger

# --- beeplex location ---
# my-agent lives inside the beeplex repo, so the checkout root is the third
# parent of this file. Override with BEEPLEX_DIR if you ever separate them.
BEEPLEX_DIR = Path(
    os.environ.get("BEEPLEX_DIR", Path(__file__).resolve().parents[3])
).resolve()


def _beeplex():
    """Import bee_fetcher from the beeplex checkout (adds it to sys.path)."""
    if not BEEPLEX_DIR.is_dir():
        raise RuntimeError(
            f"beeplex folder not found at {BEEPLEX_DIR} "
            "(set BEEPLEX_DIR to point at your checkout)"
        )
    if str(BEEPLEX_DIR) not in sys.path:
        sys.path.insert(0, str(BEEPLEX_DIR))
    import bee_fetcher

    return bee_fetcher


# --- Tools ---

@tool
def fetch_conversations(limit: int = 5) -> str:
    """Fetch the most recent Bee conversations.

    Args:
        limit: Max conversations to fetch (default 5)

    Returns:
        One line per conversation: recording date, session title, key topic.
        Also reports whether the data is live (Bee CLI) or mock fallback.
    """
    bee_fetcher = _beeplex()
    rows, info = bee_fetcher.fetch_report_data(limit=limit)
    lines = [f"mode={info['mode']} ({info['detail']})"]
    if not rows:
        lines.append("No conversations found.")
    for row in rows:
        lines.append(
            f"- {row.get('Recording_Date') or 'no date'} | "
            f"{row.get('Session_Title')} | topic: {row.get('Key_Topic')}"
        )
    return "\n".join(lines)


@tool
def score_conversations(limit: int = 5) -> str:
    """Score the most recent Bee conversations for engagement and forward motion.

    Runs beeplex's full scoring pipeline (deterministic + temporal signals,
    plus the LLM layer when a key is configured) and reports each
    conversation's engagement level, forward motion, and tone.

    Args:
        limit: Max conversations to score (default 5)

    Returns:
        Per-conversation engagement / forward-motion / tone ratings.
    """
    bee_fetcher = _beeplex()
    rows, info = bee_fetcher.fetch_report_data(limit=limit)
    lines = [f"mode={info['mode']} ({info['detail']})"]
    if not rows:
        lines.append("No conversations found.")
    for row in rows:
        lines.append(
            f"- {row.get('Session_Title')}:\n"
            f"    Engagement: {row.get('Engagement_Level')}\n"
            f"    Forward motion: {row.get('Forward_Motion')}\n"
            f"    Tone: {row.get('Tone_Rating')}"
        )
    return "\n".join(lines)


@tool
def generate_report(limit: int = 10) -> str:
    """Generate the beeplex Word/Excel/PowerPoint reports into family/.

    Runs family.py in the beeplex checkout, which fetches the latest
    conversations, scores them, and writes the transcript log (.docx),
    metrics spreadsheet (.xlsx), and insights deck (.pptx), plus regenerates
    the coaching dashboard (family/dashboard.html).

    Args:
        limit: Max conversations to include (default 10)

    Returns:
        The files that were written, and the data source used.
    """
    bee_fetcher = _beeplex()  # validates BEEPLEX_DIR exists
    del bee_fetcher
    family_dir = BEEPLEX_DIR / "family"
    before = {p.name for p in family_dir.glob("*")} if family_dir.is_dir() else set()
    proc = subprocess.run(
        [sys.executable, "family.py"],
        cwd=BEEPLEX_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        return f"Report generation failed:\n{proc.stderr[-2000:]}"
    after = {p.name for p in family_dir.glob("*")} if family_dir.is_dir() else set()
    new_files = sorted(after - before)
    lines = ["Report generation succeeded."]
    if proc.stdout.strip():
        lines.append(proc.stdout.strip().splitlines()[-5:])
    if new_files:
        lines.append("New files in family/:")
        lines.extend(f"- {name}" for name in new_files)
    return "\n".join(str(line) for line in lines)


@tool
def bee_diary(limit: int = 3) -> str:
    """Read Bee's diary entry for today.

    Runs beeplex's persona mode: derives who Bee has become from your history
    (maturity, temperament, what it notices, what it remembers) and writes
    tonight's first-person diary entry to family/Bee_YYYY-MM-DD.md.

    Args:
        limit: Max conversations from today to reflect on (default 3)

    Returns:
        Bee's diary entry for today, in Bee's own voice.
    """
    _beeplex()  # validates BEEPLEX_DIR exists
    from datetime import date

    proc = subprocess.run(
        [sys.executable, "bee_fetcher.py", "--persona", "--limit", str(limit)],
        cwd=BEEPLEX_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        return f"Diary generation failed:\n{proc.stderr[-2000:]}"
    path = BEEPLEX_DIR / "family" / f"Bee_{date.today().isoformat()}.md"
    if not path.is_file():
        return "Diary ran but no entry file was written."
    return path.read_text()


# --- Agent Setup ---

SYSTEM_PROMPT = """You are a copilot for the user's Bee hackathon project (beeplex).

Beeplex pulls the user's real-life conversations from their Bee wearable,
scores each one for engagement (heat) and forward motion (whether the heat
cooks anything), and generates Word/Excel/PowerPoint reports plus a coaching
dashboard in the family/ folder.

You have access to:
1. fetch_conversations(limit) - list recent Bee conversations with dates and topics
2. score_conversations(limit) - engagement, forward-motion, and tone ratings per conversation
3. generate_report(limit) - build the .docx/.xlsx/.pptx reports and refresh the dashboard
4. bee_diary(limit) - read Bee's diary entry for today, in Bee's own first-person voice

Rules:
- Always use the tools rather than guessing about the user's conversations.
- If a tool reports mock mode, say so plainly: the Bee CLI isn't connected,
  so the data is clearly-labelled demo data, not the user's real conversations.
- The family/ folder is gitignored and may contain real transcripts: never
  paste transcript contents into chat, only summaries, scores, and file names.
- Clinical summaries (--clinical) are not wired up yet; say so if asked."""

_agent = None


def get_or_create_agent():
    global _agent
    if _agent is None:
        _agent = Agent(
            model=load_model(),
            system_prompt=SYSTEM_PROMPT,
            tools=[fetch_conversations, score_conversations, generate_report],
        )
    return _agent


@app.entrypoint
async def invoke(payload, context):
    log.info("Invoking Agent...")
    agent = get_or_create_agent()
    stream = agent.stream_async(payload.get("prompt"))
    async for event in stream:
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]


if __name__ == "__main__":
    app.run()
