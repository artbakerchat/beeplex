"""Read-only Bee CLI data sources for beeplex (the plumbing layer).

Thin wrappers over the official Bee CLI's *read* commands, following the
same contract as ``bee_fetcher``:

* live mode -- the ``bee`` binary is on PATH and authenticated
  (``bee me --json`` succeeds). Real payloads are returned as parsed JSON.
* mock mode -- explicitly enabled with ``BEEPLEX_DEMO=1`` or ``BEEX_MOCK=1``.
  Returns clearly-labelled sample payloads for offline use.

This layer is deliberately READ-ONLY (user's standing call, 2026-09-23):
no ``facts create/update/delete``, no ``todos create/complete/...``.
Beeplex observes and scores; it never modifies the owner's Bee state.
The write commands are excluded on purpose -- see the "second reader"
note in the integration concept.

Payload shapes follow the official bee-skill docs (bee-computer/bee-skill):
verbatim utterances are authoritative; AI summaries may contain minor
inaccuracies. Each function returns the parsed ``--json`` payload (dict),
and raises BeeError when the live CLI command fails.

Mock payloads are derived from a small set of scripted mock conversations
so every source tells a coherent story in mock mode.
"""

import time

from .bee_fetcher import (
    BEE_CMD,  # noqa: F401  (re-exported: override the CLI binary)
    DEFAULT_TIMEOUT,
    MOCK_FORCED,
    _run_bee,
)


def _live():
    """True when we should call the real CLI (not mock)."""
    # Let each command report its own error. Never cache failed auth in a
    # long-running server or silently substitute demo memories.
    return not MOCK_FORCED


def _get(*args, mock):
    """Run `bee <args> --json`, or return the mock payload."""
    if not _live():
        return mock()
    return _run_bee(*args, timeout=DEFAULT_TIMEOUT)


# --- mock data -----------------------------------------------------------
# Small, coherent, clearly-labelled. Shapes mirror the real API.

_NOW_MS = lambda: int(time.time() * 1000)  # noqa: E731
_HOUR = 3_600_000


def _mock_conversations():
    now = _NOW_MS()
    return [
        {
            "id": "mock-conv-1",
            "title": "[MOCK] Sync with Priya",
            "summary": "[MOCK] Planning session about the launch timeline.",
            "start_time": now - 2 * _HOUR,
            "state": "READY",
            "utterances": [
                {
                    "speaker": "You",
                    "text": "[MOCK] So if we move the launch to Thursday we're fine?",
                    "timestamp": now - 2 * _HOUR,
                },
                {
                    "speaker": "Priya",
                    "text": "[MOCK] Thursday works, but the demo script needs a rewrite.",
                    "timestamp": now - 2 * _HOUR + 60_000,
                },
            ],
        },
        {
            "id": "mock-conv-2",
            "title": "[MOCK] Call with the accountant",
            "summary": "[MOCK] Quarterly taxes and receipt organization.",
            "start_time": now - 5 * _HOUR,
            "state": "READY",
            "utterances": [
                {
                    "speaker": "You",
                    "text": "[MOCK] I still haven't sorted the March receipts.",
                    "timestamp": now - 5 * _HOUR,
                },
            ],
        },
        {
            "id": "mock-conv-3",
            "title": "[MOCK] Dinner with Sam",
            "summary": "[MOCK] Catching up; Sam's marathon training.",
            "start_time": now - 26 * _HOUR,
            "state": "READY",
            "utterances": [
                {
                    "speaker": "Sam",
                    "text": "[MOCK] Sixteen kilometers this weekend, easy pace.",
                    "timestamp": now - 26 * _HOUR,
                },
            ],
        },
    ]


def _mock_conv_summaries():
    return [
        {k: c[k] for k in ("id", "title", "summary", "start_time", "state")}
        for c in _mock_conversations()
    ]


# --- recency -------------------------------------------------------------


def now():
    """Conversations from the last 10 hours, with full verbatim utterances."""
    return _get(
        "now",
        mock=lambda: {
            "conversations": [
                c
                for c in _mock_conversations()
                if _NOW_MS() - c["start_time"] <= 10 * _HOUR
            ]
        },
    )


def today(context=False):
    """Today's brief; with context=True, the aggregated wearable context
    (daily summary + active todos + notes + recent conversations)."""
    args = ["today"] + (["--context"] if context else [])
    return _get(
        *args,
        mock=lambda: {
            "date": time.strftime("%Y-%m-%d"),
            "brief": "[MOCK] Two meetings today: launch sync at 10, dentist at 4.",
            **(
                {
                    "daily_summary": "[MOCK] A planning-heavy day.",
                    "active_todos": _mock_todos(),
                    "recent_conversations": _mock_conv_summaries()[:2],
                }
                if context
                else {}
            ),
        },
    )


def activity(limit=20):
    """Unified recent feed across conversations, summaries, notes, todos."""
    return _get(
        "activity",
        "--limit",
        str(limit),
        mock=lambda: {
            "items": [
                {"type": "conversation", **s} for s in _mock_conv_summaries()[:limit]
            ]
            + [{"type": "todo", **t} for t in _mock_todos()[: max(0, limit - 2)]],
        },
    )


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

    def _mock():
        q = query.lower()
        hits = [
            c
            for c in _mock_conversations()
            if q in c["title"].lower()
            or q in c["summary"].lower()
            or any(q in u["text"].lower() for u in c["utterances"])
        ]
        hits = [
            c
            for c in hits
            if (since is None or c["start_time"] >= int(since))
            and (until is None or c["start_time"] <= int(until))
        ][:limit]
        return {
            "query": query,
            "mode": "keyword",
            "note": "Demo search uses keyword matching, including when semantic search is requested.",
            "results": [
                {k: c[k] for k in ("id", "title", "summary", "start_time", "state")}
                for c in hits
            ],
        }

    return _get(*args, mock=_mock)


# --- conversations -------------------------------------------------------


def conversation_transcript(conv_id):
    """Just the verbatim utterance transcript for one conversation."""
    return _get(
        "conversations",
        "transcript",
        str(conv_id),
        mock=lambda: {
            "id": conv_id,
            "utterances": next(
                (c["utterances"] for c in _mock_conversations() if c["id"] == conv_id),
                [],
            ),
        },
    )


def conversations_related(conv_id, limit=10):
    """Conversations similar to the given one (a topic thread)."""
    return _get(
        "conversations",
        "related",
        str(conv_id),
        "--limit",
        str(limit),
        mock=lambda: {
            "id": conv_id,
            "related": [s for s in _mock_conv_summaries() if s["id"] != conv_id][
                :limit
            ],
        },
    )


# --- daily summaries -----------------------------------------------------


def _mock_daily():
    convs = _mock_conversations()
    days = {}
    for c in convs:
        day = time.strftime("%Y-%m-%d", time.localtime(c["start_time"] / 1000))
        days.setdefault(day, []).append(c["title"])
    return [
        {
            "id": f"mock-daily-{d}",
            "date": d,
            "summary": "[MOCK] " + "; ".join(titles),
        }
        for d, titles in sorted(days.items(), reverse=True)
    ]


def daily_list(limit=10, cursor=None):
    """Browse day-by-day summaries, newest first."""
    args = ["daily", "list", "--limit", str(limit)]
    if cursor:
        args += ["--cursor", cursor]
    return _get(
        *args,
        mock=lambda: {"daily": _mock_daily()[:limit], "next_cursor": None},
    )


def daily_get(daily_id):
    """One daily summary by id."""
    return _get(
        "daily",
        "get",
        str(daily_id),
        mock=lambda: next((d for d in _mock_daily() if d["id"] == daily_id), None),
    )


def daily_find(date_str):
    """Look up the daily summary for a YYYY-MM-DD date."""
    return _get(
        "daily",
        "find",
        date_str,
        mock=lambda: next((d for d in _mock_daily() if d["date"] == date_str), None),
    )


# --- journals (intentional voice memos) ----------------------------------


def _mock_journals():
    now = _NOW_MS()
    return [
        {
            "id": "mock-journal-1",
            "state": "READY",
            "text": "[MOCK] Idea: coach on forward motion, not just engagement.",
            "timestamp": now - 3 * _HOUR,
        },
        {
            "id": "mock-journal-2",
            "state": "READY",
            "text": "[MOCK] Remember to ask Priya about the demo script.",
            "timestamp": now - 30 * _HOUR,
        },
    ]


def journals_list(limit=10, cursor=None):
    """The owner's intentional voice memos (distinct from ambient audio)."""
    args = ["journals", "list", "--limit", str(limit)]
    if cursor:
        args += ["--cursor", cursor]
    return _get(
        *args,
        mock=lambda: {"journals": _mock_journals()[:limit], "next_cursor": None},
    )


def journals_search(query, limit=10):
    """Find a voice memo by content."""
    return _get(
        "journals",
        "search",
        "--query",
        query,
        "--limit",
        str(limit),
        mock=lambda: {
            "query": query,
            "journals": [
                j for j in _mock_journals() if query.lower() in j["text"].lower()
            ][:limit],
        },
    )


def journals_get(journal_id):
    """Full transcribed text of one voice memo."""
    return _get(
        "journals",
        "get",
        str(journal_id),
        mock=lambda: next((j for j in _mock_journals() if j["id"] == journal_id), None),
    )


# --- insights (Bee's AI-generated patterns) ------------------------------


def _mock_insights():
    return [
        {
            "id": "mock-insight-1",
            "title": "[MOCK] Thursday planning pattern",
            "text": "[MOCK] Your Thursday conversations run 40% longer and "
            "circle back to timelines twice on average.",
        },
        {
            "id": "mock-insight-2",
            "title": "[MOCK] Quiet mornings",
            "text": "[MOCK] You speak least before 9am; your longest turns "
            "happen after lunch.",
        },
    ]


def insights_list(limit=50):
    """AI-generated patterns and observations about the owner."""
    return _get(
        "insights",
        "list",
        "--limit",
        str(limit),
        mock=lambda: {"insights": _mock_insights()[:limit]},
    )


def insights_get(insight_id):
    """One insight by id."""
    return _get(
        "insights",
        "get",
        str(insight_id),
        mock=lambda: next((i for i in _mock_insights() if i["id"] == insight_id), None),
    )


# --- locations -----------------------------------------------------------


def _mock_places():
    return [
        {"name": "[MOCK] Home", "visits": 42},
        {"name": "[MOCK] Bluebird Cafe", "visits": 7},
    ]


def locations_recent(from_date=None, to_date=None, limit=100):
    """Where the owner has been. Dates are YYYY-MM-DD or ISO."""
    args = ["locations", "recent", "--limit", str(limit)]
    if from_date:
        args += ["--from", from_date]
    if to_date:
        args += ["--to", to_date]
    return _get(
        *args,
        mock=lambda: {
            "visits": [
                {"place": p["name"], "timestamp": _NOW_MS() - i * _HOUR * 5}
                for i, p in enumerate(_mock_places() * 3)
            ][:limit],
        },
    )


def locations_clusters(limit=20, min_visits=None, visits=False):
    """Frequently visited places."""
    args = ["locations", "clusters", "--limit", str(limit)]
    if min_visits is not None:
        args += ["--min-visits", str(min_visits)]
    if visits:
        args.append("--visits")
    return _get(
        *args,
        mock=lambda: {
            "clusters": [
                p
                for p in _mock_places()
                if min_visits is None or p["visits"] >= min_visits
            ][:limit],
        },
    )


def locations_current():
    """Latest known location."""
    return _get(
        "locations",
        "current",
        mock=lambda: {"place": "[MOCK] Home", "timestamp": _NOW_MS()},
    )


# --- facts (Bee's learned profile; read-only) ----------------------------


def _mock_facts():
    return [
        {
            "id": "mock-fact-1",
            "text": "[MOCK] Prefers morning meetings.",
            "confirmed": True,
        },
        {
            "id": "mock-fact-2",
            "text": "[MOCK] Works on the Bee hackathon project.",
            "confirmed": True,
        },
        {
            "id": "mock-fact-3",
            "text": "[MOCK] Might be training for a marathon.",
            "confirmed": False,
        },
    ]


def facts_list(limit=10, cursor=None, unconfirmed=False):
    """What Bee has learned about the owner. Confirmed facts are verified;
    unconfirmed are inferred and may be misinterpretations."""
    args = ["facts", "list", "--limit", str(limit)]
    if cursor:
        args += ["--cursor", cursor]
    if unconfirmed:
        args.append("--unconfirmed")
    return _get(
        *args,
        mock=lambda: {
            "facts": [f for f in _mock_facts() if unconfirmed or f["confirmed"]][
                :limit
            ],
            "next_cursor": None,
        },
    )


def facts_get(fact_id):
    """One fact by id."""
    return _get(
        "facts",
        "get",
        str(fact_id),
        mock=lambda: next((f for f in _mock_facts() if f["id"] == fact_id), None),
    )


def facts_search(query, limit=10):
    """Find facts by content."""
    return _get(
        "facts",
        "search",
        "--query",
        query,
        "--limit",
        str(limit),
        mock=lambda: {
            "query": query,
            "facts": [f for f in _mock_facts() if query.lower() in f["text"].lower()][
                :limit
            ],
        },
    )


# --- todos (read-only; suggestions included) -----------------------------


def _mock_todos():
    return [
        {
            "id": "mock-todo-1",
            "text": "[MOCK] Rewrite the demo script before Thursday.",
            "completed": False,
        },
        {
            "id": "mock-todo-2",
            "text": "[MOCK] Sort the March receipts.",
            "completed": False,
        },
    ]


def _mock_suggestions():
    return [
        {
            "id": "mock-sugg-1",
            "text": "[MOCK] Suggested: ask Priya about the timeline risk.",
            "conversation_id": "mock-conv-1",
        },
    ]


def todos_list(limit=10, cursor=None):
    """Action items and commitments."""
    args = ["todos", "list", "--limit", str(limit)]
    if cursor:
        args += ["--cursor", cursor]

    def demo_page():
        try:
            offset = int(cursor or 0)
            if offset < 0:
                raise ValueError
        except ValueError:
            from .client import BeeError

            raise BeeError(
                "Invalid demo cursor. Use next_cursor from the previous response."
            ) from None
        items = _mock_todos()
        return {
            "todos": items[offset : offset + limit],
            "next_cursor": str(offset + limit) if offset + limit < len(items) else None,
        }

    return _get(
        *args,
        mock=demo_page,
    )


def todos_get(todo_id):
    """One todo by id."""
    return _get(
        "todos",
        "get",
        str(todo_id),
        mock=lambda: next((t for t in _mock_todos() if t["id"] == todo_id), None),
    )


def todos_suggestions(limit=50):
    """Todos Bee proposed from conversations, not yet accepted."""
    return _get(
        "todos",
        "suggestions",
        "--limit",
        str(limit),
        mock=lambda: {"suggestions": _mock_suggestions()[:limit]},
    )


# --- changefeed ----------------------------------------------------------


def changed(cursor=None):
    """What changed since the last check (facts, todos, daily summaries,
    conversations, journals). Persist the returned next_cursor only AFTER
    processing the batch, so a failure retries the same changes
    (exactly-once)."""
    args = ["changed"] + (["--cursor", cursor] if cursor else [])
    return _get(
        *args,
        mock=lambda: {
            "cursor": cursor,
            "next_cursor": "mock-cursor-1",
            "conversations": _mock_conv_summaries()[:1],
            "facts": _mock_facts()[:1],
            "todos": _mock_todos()[:1],
            "daily": _mock_daily()[:1],
            "journals": [],
        },
    )


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
