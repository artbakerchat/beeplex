#!/usr/bin/env python3
"""Demo stand-in for the Bee CLI, used by ``beeplex --demo``.

Speaks the same argv/JSON contract as the real Bee CLI but serves
clearly-labelled sample memories. Because the demo is a *CLI*, not a code
branch, it runs through the exact same subprocess path as live mode
(``beeplex.client.run``) -- there is no separate mock branch anywhere in
beeplex, so the demo exercises the real data handling.

Invoked as ``demo_cli.py <command> [args] [--json]``; ``--json`` is
accepted and ignored (output is always JSON).
"""

import json
import sys
import time

_NOW_MS = lambda: int(time.time() * 1000)  # noqa: E731
_HOUR = 3_600_000


# --- sample dataset ------------------------------------------------------
# Small, coherent, clearly-labelled. Shapes mirror the real Bee CLI.


def _conversations():
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


def _conv_summaries():
    return [
        {k: c[k] for k in ("id", "title", "summary", "start_time", "state")}
        for c in _conversations()
    ]


def _todos():
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


def _suggestions():
    return [
        {
            "id": "mock-sugg-1",
            "text": "[MOCK] Suggested: ask Priya about the timeline risk.",
            "conversation_id": "mock-conv-1",
        },
    ]


def _journals():
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


def _insights():
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


def _places():
    return [
        {"name": "[MOCK] Home", "visits": 42},
        {"name": "[MOCK] Bluebird Cafe", "visits": 7},
    ]


def _facts():
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


def _daily():
    days = {}
    for c in _conversations():
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


# --- argv handling -------------------------------------------------------


def _opt(argv, *names, default=None):
    for i, token in enumerate(argv):
        if token in names and i + 1 < len(argv):
            return argv[i + 1]
    return default


def _has(argv, *names):
    return any(token in names for token in argv)


def _fail(message):
    sys.stderr.write(f"demo_cli: {message}\n")
    sys.exit(1)


def _page(items, argv):
    """Offset-cursor pagination shared by list commands."""
    limit = int(_opt(argv, "--limit", default="10"))
    cursor = _opt(argv, "--cursor")
    try:
        offset = int(cursor) if cursor is not None else 0
        if offset < 0:
            raise ValueError
    except ValueError:
        _fail("Invalid cursor. Use next_cursor from the previous response.")
    return (
        items[offset : offset + limit],
        str(offset + limit) if offset + limit < len(items) else None,
    )


# --- command handlers ----------------------------------------------------


def _me(positional, argv):
    return {"id": "demo-user", "name": "[MOCK] Demo User", "demo": True}


def _now(positional, argv):
    now = _NOW_MS()
    return {
        "conversations": [
            c for c in _conversations() if now - c["start_time"] <= 10 * _HOUR
        ]
    }


def _today(positional, argv):
    payload = {
        "date": time.strftime("%Y-%m-%d"),
        "brief": "[MOCK] Two meetings today: launch sync at 10, dentist at 4.",
    }
    if _has(argv, "--context"):
        payload.update(
            {
                "daily_summary": "[MOCK] A planning-heavy day.",
                "active_todos": _todos(),
                "recent_conversations": _conv_summaries()[:2],
            }
        )
    return payload


def _activity(positional, argv):
    limit = int(_opt(argv, "--limit", default="20"))
    return {
        "items": [{"type": "conversation", **s} for s in _conv_summaries()[:limit]]
        + [{"type": "todo", **t} for t in _todos()[: max(0, limit - 2)]],
    }


def _search(positional, argv):
    query = _opt(argv, "--query", default="")
    limit = int(_opt(argv, "--limit", default="10"))
    since = _opt(argv, "--since")
    until = _opt(argv, "--until")
    q = query.lower()
    hits = [
        c
        for c in _conversations()
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


def _conversations_list(positional, argv):
    items, next_cursor = _page(_conv_summaries(), argv)
    return {"conversations": items, "next_cursor": next_cursor}


def _conversations_get(positional, argv):
    conv_id = positional[0] if positional else None
    conv = next((c for c in _conversations() if c["id"] == conv_id), None)
    return {"conversation": conv}


def _conversations_transcript(positional, argv):
    conv_id = positional[0] if positional else None
    utterances = next(
        (c["utterances"] for c in _conversations() if c["id"] == conv_id), []
    )
    return {"id": conv_id, "utterances": utterances}


def _conversations_related(positional, argv):
    conv_id = positional[0] if positional else None
    limit = int(_opt(argv, "--limit", default="10"))
    return {
        "id": conv_id,
        "related": [s for s in _conv_summaries() if s["id"] != conv_id][:limit],
    }


def _daily_list(positional, argv):
    items, next_cursor = _page(_daily(), argv)
    return {"daily": items, "next_cursor": next_cursor}


def _daily_get(positional, argv):
    daily_id = positional[0] if positional else None
    return next((d for d in _daily() if d["id"] == daily_id), None)


def _daily_find(positional, argv):
    date_str = positional[0] if positional else None
    return next((d for d in _daily() if d["date"] == date_str), None)


def _journals_list(positional, argv):
    items, next_cursor = _page(_journals(), argv)
    return {"journals": items, "next_cursor": next_cursor}


def _journals_search(positional, argv):
    query = _opt(argv, "--query", default="")
    limit = int(_opt(argv, "--limit", default="10"))
    return {
        "query": query,
        "journals": [j for j in _journals() if query.lower() in j["text"].lower()][
            :limit
        ],
    }


def _journals_get(positional, argv):
    journal_id = positional[0] if positional else None
    return next((j for j in _journals() if j["id"] == journal_id), None)


def _insights_list(positional, argv):
    limit = int(_opt(argv, "--limit", default="50"))
    return {"insights": _insights()[:limit]}


def _insights_get(positional, argv):
    insight_id = positional[0] if positional else None
    return next((i for i in _insights() if i["id"] == insight_id), None)


def _locations_recent(positional, argv):
    limit = int(_opt(argv, "--limit", default="100"))
    now = _NOW_MS()
    return {
        "visits": [
            {"place": p["name"], "timestamp": now - i * _HOUR * 5}
            for i, p in enumerate(_places() * 3)
        ][:limit],
    }


def _locations_clusters(positional, argv):
    limit = int(_opt(argv, "--limit", default="20"))
    min_visits = _opt(argv, "--min-visits")
    return {
        "clusters": [
            p
            for p in _places()
            if min_visits is None or p["visits"] >= int(min_visits)
        ][:limit],
    }


def _locations_current(positional, argv):
    return {"place": "[MOCK] Home", "timestamp": _NOW_MS()}


def _facts_list(positional, argv):
    limit = int(_opt(argv, "--limit", default="10"))
    unconfirmed = _has(argv, "--unconfirmed")
    items, next_cursor = _page(
        [f for f in _facts() if unconfirmed or f["confirmed"]], argv
    )
    return {"facts": items, "next_cursor": next_cursor}


def _facts_get(positional, argv):
    fact_id = positional[0] if positional else None
    return next((f for f in _facts() if f["id"] == fact_id), None)


def _facts_search(positional, argv):
    query = _opt(argv, "--query", default="")
    limit = int(_opt(argv, "--limit", default="10"))
    return {
        "query": query,
        "facts": [f for f in _facts() if query.lower() in f["text"].lower()][:limit],
    }


def _todos_list(positional, argv):
    items, next_cursor = _page(_todos(), argv)
    return {"todos": items, "next_cursor": next_cursor}


def _todos_get(positional, argv):
    todo_id = positional[0] if positional else None
    return next((t for t in _todos() if t["id"] == todo_id), None)


def _todos_suggestions(positional, argv):
    limit = int(_opt(argv, "--limit", default="50"))
    return {"suggestions": _suggestions()[:limit]}


def _changed(positional, argv):
    cursor = _opt(argv, "--cursor")
    return {
        "cursor": cursor,
        "next_cursor": "mock-cursor-1",
        "conversations": _conv_summaries()[:1],
        "facts": _facts()[:1],
        "todos": _todos()[:1],
        "daily": _daily()[:1],
        "journals": [],
    }


_COMMANDS = {
    ("me",): _me,
    ("now",): _now,
    ("today",): _today,
    ("activity",): _activity,
    ("search",): _search,
    ("conversations", "list"): _conversations_list,
    ("conversations", "get"): _conversations_get,
    ("conversations", "transcript"): _conversations_transcript,
    ("conversations", "related"): _conversations_related,
    ("daily", "list"): _daily_list,
    ("daily", "get"): _daily_get,
    ("daily", "find"): _daily_find,
    ("journals", "list"): _journals_list,
    ("journals", "search"): _journals_search,
    ("journals", "get"): _journals_get,
    ("insights", "list"): _insights_list,
    ("insights", "get"): _insights_get,
    ("locations", "recent"): _locations_recent,
    ("locations", "clusters"): _locations_clusters,
    ("locations", "current"): _locations_current,
    ("facts", "list"): _facts_list,
    ("facts", "get"): _facts_get,
    ("facts", "search"): _facts_search,
    ("todos", "list"): _todos_list,
    ("todos", "get"): _todos_get,
    ("todos", "suggestions"): _todos_suggestions,
    ("changed",): _changed,
}


def main(argv):
    # Strip flags to find the command words, e.g.
    # ["conversations", "list", "--limit", "5", "--json"] -> ("conversations", "list")
    words = [t for t in argv if not t.startswith("-")]
    handler = None
    positional = []
    for n in (2, 1):
        key = tuple(words[:n])
        if key in _COMMANDS:
            handler = _COMMANDS[key]
            positional = words[n:]
            break
    if handler is None:
        _fail(f"unknown command: {' '.join(words)}")
    payload = handler(positional, argv)
    sys.stdout.write(json.dumps(payload))


if __name__ == "__main__":
    main(sys.argv[1:])
