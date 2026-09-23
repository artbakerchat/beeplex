"""beeplex tool implementations, transport-agnostic.

The five copilot tools live here as plain functions with no dependency on
strands, AgentCore, or MCP. Each transport wraps them thinly:

* ``main.py`` exposes them as strands ``@tool``s for the AgentCore agent.
* ``mcp_server.py`` exposes them as MCP tools over stdio (like
  ``bee mcp serve``), so any MCP-aware client can drive beeplex directly.

Adding a tool: implement ``<name>_impl(...)`` here, then register it in
each transport you want it on. Keep every function JSON-safe (str in/out)
and never paste transcript contents into returned text -- summaries,
scores, and file names only (family/ is gitignored and may hold real
transcripts).
"""

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

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


def fetch_conversations_impl(limit: int = 5) -> str:
    """Fetch the most recent Bee conversations.

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


def score_conversations_impl(limit: int = 5) -> str:
    """Score the most recent Bee conversations for engagement and forward motion.

    Runs beeplex's full scoring pipeline (deterministic + temporal signals,
    plus the LLM layer when a key is configured) and reports each
    conversation's engagement level, forward motion, and tone.
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


def generate_report_impl(limit: int = 10) -> str:
    """Generate the beeplex Word/Excel/PowerPoint reports into family/.

    Runs family.py in the beeplex checkout, which fetches the latest
    conversations, scores them, and writes the transcript log (.docx),
    metrics spreadsheet (.xlsx), and insights deck (.pptx), plus regenerates
    the coaching dashboard (family/dashboard.html).
    """
    _beeplex()  # validates BEEPLEX_DIR exists
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


def bee_diary_impl(limit: int = 3) -> str:
    """Read Bee's diary entry for today.

    Runs beeplex's persona mode: derives who Bee has become from your history
    (maturity, temperament, what it notices, what it remembers) and writes
    tonight's first-person diary entry to family/Bee_YYYY-MM-DD.md.
    """
    _beeplex()  # validates BEEPLEX_DIR exists
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


def user_profile_impl(full: bool = False, limit: int = 50) -> str:
    """Build/update the user's living profile (family/user.md).

    Runs profile.py's incremental builder: new conversations since the last
    run are folded into family/profile_state.json, then the whole user.md
    is re-rendered from state plus fresh static data (Bee facts, insights,
    journals, places). Returns the profile text itself.
    """
    _beeplex()  # validates BEEPLEX_DIR exists
    if str(BEEPLEX_DIR) not in sys.path:
        sys.path.insert(0, str(BEEPLEX_DIR))
    import profile

    path, info = profile.run_profile(full=full, limit=limit)
    header = (
        f"mode={info['mode']} new_conversations={info['new_conversations']} "
        f"total_conversations={info['total_conversations']} "
        f"facts={info['facts']}\n"
        f"--- {path} ---\n"
    )
    return header + Path(path).read_text()
