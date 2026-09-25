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
from pathlib import Path

_NOW_MS = lambda: int(time.time() * 1000)  # noqa: E731
_HOUR = 3_600_000
_MINUTE = 60_000


# --- sample dataset ------------------------------------------------------
# The nine simulator scenarios (simulator/conversations.json) are the single
# source of truth for demo data -- the same scenarios behind the voice
# editor's aggregate page and the scoring benchmark. They are served with
# [MOCK] labels so demo output is never mistaken for real memories.


def _conversations():
    now = _NOW_MS()
    path = Path(__file__).resolve().parent.parent / "simulator" / "conversations.json"
    try:
        scenarios = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        scenarios = []
    conversations = []
    for s in scenarios if isinstance(scenarios, list) else []:
        if not isinstance(s, dict):
            continue
        utterances = []
        for u in s.get("utterances") or []:
            minutes = u.get("minutes_ago")
            stamp = (
                now - int(minutes) * _MINUTE
                if isinstance(minutes, (int, float))
                else now
            )
            utterances.append(
                {
                    "speaker": u.get("speaker") or "Speaker 1",
                    "text": "[MOCK] " + str(u.get("text") or ""),
                    "timestamp": stamp,
                }
            )
        start_minutes = s.get("minutes_ago")
        conversations.append(
            {
                "id": s.get("id") or "sim-conversation",
                "title": "[MOCK] " + str(s.get("title") or "Untitled"),
                "summary": "[MOCK] " + str(s.get("summary") or ""),
                "start_time": (
                    now - int(start_minutes) * _MINUTE
                    if isinstance(start_minutes, (int, float))
                    else now
                ),
                "state": "READY",
                "utterances": utterances,
            }
        )
    # Newest first, like the real CLI.
    conversations.sort(key=lambda c: c["start_time"], reverse=True)
    return conversations


def _conv_summaries():
    return [
        {k: c[k] for k in ("id", "title", "summary", "start_time", "state")}
        for c in _conversations()
    ]


def _todos():
    return [
        {
            "id": "sim-todo-1",
            "text": "[MOCK] Revisit the holiday plans disagreement.",
            "completed": False,
        },
        {
            "id": "sim-todo-2",
            "text": "[MOCK] Decide the launch date after the product debate.",
            "completed": False,
        },
    ]


def _suggestions():
    return [
        {
            "id": "sim-sugg-1",
            "text": "[MOCK] Suggested: ask about the timeline risk in the launch debate.",
            "conversation_id": "sim_debate",
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
        "next_cursor": "sim-cursor-1",
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
