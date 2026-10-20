"""my-agent: a copilot for the beeplex folder.

Instead of the 00-getting-started sample's customer-support tools, this agent's
tools drive the user's Bee hackathon project (beeplex): fetching today's Bee
conversations, scoring them, generating the Word/Excel/PowerPoint reports,
reading Bee's diary (the persona mode), and maintaining the user's living
profile (family/user.md).

Wrapped in BedrockAgentCoreApp so it runs both locally (agentcore dev) and on
AgentCore Runtime (agentcore deploy). The model is loaded from model/load.py,
which defaults to ca.amazon.nova-micro-v1:0 in ca-central-1.
"""

from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from model.load import load_model
from my_agent.tools import (
    BEEPLEX_DIR,  # re-exported: ui/app.py imports these from here
    _beeplex,  # re-exported: ui/app.py imports these from here
    bee_diary_impl,
    fetch_conversations_impl,
    generate_report_impl,
    score_conversations_impl,
    user_profile_impl,
)

app = BedrockAgentCoreApp()

log = app.logger


# --- Tools ---
# Implementations live in my_agent/tools.py (shared with the MCP server);
# these are thin strands wrappers over them.

@tool
def fetch_conversations(limit: int = 5) -> str:
    """Fetch the most recent Bee conversations.

    Args:
        limit: Max conversations to fetch (default 5)

    Returns:
        One line per conversation: recording date, session title, key topic.
        Also reports whether the data is live (Bee CLI) or mock fallback.
    """
    return fetch_conversations_impl(limit=limit)


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
    return score_conversations_impl(limit=limit)


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
    return generate_report_impl(limit=limit)


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
    return bee_diary_impl(limit=limit)


@tool
def user_profile(full: bool = False, limit: int = 50) -> str:
    """Build/update the user's living profile and return it.

    Incrementally folds new Bee conversations into family/user.md (people,
    projects, preferences, events) and returns the profile text.

    Args:
        full: Rebuild from scratch instead of incrementally (default False)
        limit: Conversations to consider on a full rebuild (default 50)

    Returns:
        The user's living profile text.
    """
    return user_profile_impl(full=full, limit=limit)


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
5. user_profile(full, limit) - build/update the user's living profile (family/user.md)
   from their Bee conversations and return it

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
            tools=[fetch_conversations, score_conversations, generate_report,
                   bee_diary, user_profile],
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
