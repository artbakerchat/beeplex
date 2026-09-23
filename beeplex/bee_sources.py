"""Read-only Bee CLI data sources for beeplex (the plumbing layer).

Thin wrappers over the official Bee CLI's *read* commands. Every call goes
through ``beeplex.client.run`` -- the single subprocess path. In demo mode
(``beeplex --demo``) ``BEE_CLI`` points at the bundled fake CLI
(``beeplex/demo_cli.py``), so the exact same code serves clearly-labelled
sample data; there is no separate mock branch.

This layer is deliberately READ-ONLY (user's standing call, 2026-09-23):
no ``facts create/update/delete``, no ``todos create/complete/...``.
Beeplex observes and scores; it never modifies the owner's Bee state.
The write commands are excluded on purpose -- see the "second reader"
note in the integration concept.

Payload shapes follow the official bee-skill docs (bee-computer/bee-skill):
verbatim utterances are authoritative; AI summaries may contain minor
inaccuracies. Each function returns the parsed ``--json`` payload (dict),
and raises BeeError when the CLI command fails.
"""

from .client import run


# --- recency -------------------------------------------------------------


def now():
    """Conversations from the last 10 hours, with full verbatim utterances."""
    return run("now")


def today(context=False):
    """Today's brief; with context=True, the aggregated wearable context
    (daily summary + active todos + notes + recent conversations)."""
    args = ["today"] + (["--context"] if context else [])
    return run(*args)


def activity(limit=20):
    """Unified recent feed across conversations, summaries, notes, todos."""
    return run("activity", "--limit", str(limit))


# --- search --------------------------------------------------------------


def search(
    query,
    neural=False,
    filter="all",
    scope=None,
    sort="relevance",
    since=None,
    until=None,
    limit=10,
):
    """Server-side search. Keyword (BM25) by default; neural=True for
    semantic/vector search over conversations only.

    In neural mode the keyword-only flags (filter/scope/sort) are rejected
    by the CLI, so they are omitted here too.
    """
    args = ["search", "--query", query, "--limit", str(limit)]
    if neural:
        args.append("--neural")
    else:
        args += ["--filter", filter, "--sort", sort]
        if scope:
            args += ["--scope", scope]
    if since is not None:
        args += ["--since", str(since)]
    if until is not None:
        args += ["--until", str(until)]
    return run(*args)


# --- conversations -------------------------------------------------------


def conversation_transcript(conv_id):
    """Just the verbatim utterance transcript for one conversation."""
    return run("conversations", "transcript", str(conv_id))


def conversations_related(conv_id, limit=10):
    """Conversations similar to the given one (a topic thread)."""
    return run("conversations", "related", str(conv_id), "--limit", str(limit))


# --- daily summaries -----------------------------------------------------


def daily_list(limit=10, cursor=None):
    """Browse day-by-day summaries, newest first."""
    args = ["daily", "list", "--limit", str(limit)]
    if cursor:
        args += ["--cursor", cursor]
    return run(*args)


def daily_get(daily_id):
    """One daily summary by id."""
    return run("daily", "get", str(daily_id))


def daily_find(date_str):
    """Look up the daily summary for a YYYY-MM-DD date."""
    return run("daily", "find", date_str)


# --- journals (intentional voice memos) ----------------------------------


def journals_list(limit=10, cursor=None):
    """The owner's intentional voice memos (distinct from ambient audio)."""
    args = ["journals", "list", "--limit", str(limit)]
    if cursor:
        args += ["--cursor", cursor]
    return run(*args)


def journals_search(query, limit=10):
    """Find a voice memo by content."""
    return run("journals", "search", "--query", query, "--limit", str(limit))


def journals_get(journal_id):
    """Full transcribed text of one voice memo."""
    return run("journals", "get", str(journal_id))


# --- insights (Bee's AI-generated patterns) ------------------------------


def insights_list(limit=50):
    """AI-generated patterns and observations about the owner."""
    return run("insights", "list", "--limit", str(limit))


def insights_get(insight_id):
    """One insight by id."""
    return run("insights", "get", str(insight_id))


# --- locations -----------------------------------------------------------


def locations_recent(from_date=None, to_date=None, limit=100):
    """Where the owner has been. Dates are YYYY-MM-DD or ISO."""
    args = ["locations", "recent", "--limit", str(limit)]
    if from_date:
        args += ["--from", from_date]
    if to_date:
        args += ["--to", to_date]
    return run(*args)


def locations_clusters(limit=20, min_visits=None, visits=False):
    """Frequently visited places."""
    args = ["locations", "clusters", "--limit", str(limit)]
    if min_visits is not None:
        args += ["--min-visits", str(min_visits)]
    if visits:
        args.append("--visits")
    return run(*args)


def locations_current():
    """Latest known location."""
    return run("locations", "current")


# --- facts (Bee's learned profile; read-only) ----------------------------


def facts_list(limit=10, cursor=None, unconfirmed=False):
    """What Bee has learned about the owner. Confirmed facts are verified;
    unconfirmed are inferred and may be misinterpretations."""
    args = ["facts", "list", "--limit", str(limit)]
    if cursor:
        args += ["--cursor", cursor]
    if unconfirmed:
        args.append("--unconfirmed")
    return run(*args)


def facts_get(fact_id):
    """One fact by id."""
    return run("facts", "get", str(fact_id))


def facts_search(query, limit=10):
    """Find facts by content."""
    return run("facts", "search", "--query", query, "--limit", str(limit))


# --- todos (read-only; suggestions included) -----------------------------


def todos_list(limit=10, cursor=None):
    """Action items and commitments."""
    args = ["todos", "list", "--limit", str(limit)]
    if cursor:
        args += ["--cursor", cursor]
    return run(*args)


def todos_get(todo_id):
    """One todo by id."""
    return run("todos", "get", str(todo_id))


def todos_suggestions(limit=50):
    """Todos Bee proposed from conversations, not yet accepted."""
    return run("todos", "suggestions", "--limit", str(limit))


# --- changefeed ----------------------------------------------------------


def changed(cursor=None):
    """What changed since the last check (facts, todos, daily summaries,
    conversations, journals). Persist the returned next_cursor only AFTER
    processing the batch, so a failure retries the same changes
    (exactly-once)."""
    args = ["changed"] + (["--cursor", cursor] if cursor else [])
    return run(*args)


# Explicit read-only surface: anything not listed here is not wrapped.
__all__ = [
    "now",
    "today",
    "activity",
    "search",
    "conversation_transcript",
    "conversations_related",
    "daily_list",
    "daily_get",
    "daily_find",
    "journals_list",
    "journals_search",
    "journals_get",
    "insights_list",
    "insights_get",
    "locations_recent",
    "locations_clusters",
    "locations_current",
    "facts_list",
    "facts_get",
    "facts_search",
    "todos_list",
    "todos_get",
    "todos_suggestions",
    "changed",
]
