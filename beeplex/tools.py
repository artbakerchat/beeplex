"""Conversation-oriented operations shared by MCP and local commands."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from threading import RLock

from . import bee_fetcher as bf, bee_sources as sources
from .client import BeeError, run
from .config import DATA_DIR, DEMO

WRITE_LOCK = RLock()


def result(data, **metadata) -> dict:
    return {"mode": "demo" if DEMO else "live", "data": data, **metadata}


def _items(payload, key):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get(key, payload.get("items", [])) or []
    raise BeeError("Bee returned an unexpected response shape.")


def _summary(conv):
    return {
        "id": str(bf._conv_id(conv)) if bf._conv_id(conv) is not None else None,
        "title": conv.get("title", conv.get("name", "Untitled")),
        "summary": conv.get("summary", conv.get("description", "")),
        "start_time": conv.get("start_time"),
        "state": conv.get("state"),
    }


def fetch_conversations(limit=5, cursor=None):
    if DEMO:
        conversations = sources._mock_conv_summaries()
        try:
            offset = int(cursor or 0)
            if offset < 0:
                raise ValueError
        except ValueError:
            raise BeeError(
                "Invalid demo cursor. Use next_cursor from the previous response."
            ) from None
        next_cursor = (
            str(offset + limit) if offset + limit < len(conversations) else None
        )
        conversations = conversations[offset : offset + limit]
    else:
        args = ["conversations", "list", "--limit", str(limit)]
        if cursor:
            args += ["--cursor", cursor]
        payload = run(*args)
        conversations = _items(payload, "conversations")[:limit]
        next_cursor = payload.get("next_cursor") if isinstance(payload, dict) else None
    return result([_summary(c) for c in conversations], next_cursor=next_cursor)


def get_context(period="recent", date_str=None, limit=10):
    if period == "date":
        if not date_str:
            raise BeeError("Provide date_str as YYYY-MM-DD when period is date.")
        try:
            date.fromisoformat(date_str)
        except ValueError:
            raise BeeError(
                "date_str must be a valid calendar date in YYYY-MM-DD format."
            ) from None
        data = sources.daily_find(date_str)
    elif period == "today":
        data = sources.today(context=True)
    else:
        data = sources.now()
        conversations = _items(data, "conversations")
        return result(
            [_summary(c) for c in conversations[:limit]],
            window="last 10 hours",
            has_more=len(conversations) > limit,
            hint="Use read_conversation with an id for exact words; fetch_conversations to browse further.",
        )
    return result(data, message="No summary found." if not data else None)


def search_memories(query, limit=10, since=None, until=None, semantic=False):
    query = query.strip()
    if not query:
        raise BeeError("Provide a topic, name, or phrase to search for.")
    for value in (since, until):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise BeeError("Search dates must be valid YYYY-MM-DD dates.") from None
    if since and until and since > until:
        raise BeeError("since must be on or before until.")
    # Bee's search API expects epoch milliseconds. Calendar days use the
    # server's local timezone, with until including the whole last day.
    try:
        since_ms = (
            int(
                datetime.combine(date.fromisoformat(since), time.min).timestamp() * 1000
            )
            if since
            else None
        )
        until_ms = (
            int(
                datetime.combine(
                    date.fromisoformat(until) + timedelta(days=1), time.min
                ).timestamp()
                * 1000
            )
            - 1
            if until
            else None
        )
    except (OverflowError, OSError, ValueError):
        raise BeeError(
            "Search date is outside the supported timestamp range."
        ) from None
    payload = sources.search(
        query, neural=semantic, since=since_ms, until=until_ms, limit=limit
    )
    return result(payload, date_timezone=str(datetime.now().astimezone().tzinfo))


def read_conversation(conversation_id, offset=0, limit=50):
    if DEMO:
        conv = next(
            (c for c in sources._mock_conversations() if c["id"] == conversation_id),
            None,
        )
    else:
        conv = bf.get_conversation(conversation_id)
    if not conv:
        raise BeeError(
            "Conversation not found. Use an id returned by fetch_conversations or search_memories."
        )
    utterances = conv.get("utterances")
    if not isinstance(utterances, list):
        transcript = sources.conversation_transcript(conversation_id)
        utterances = _items(transcript, "utterances")
    end = offset + limit
    return result(
        {**_summary(conv), "utterances": utterances[offset:end]},
        next_offset=end if end < len(utterances) else None,
        total_utterances=len(utterances),
    )


def get_todos(limit=20, cursor=None):
    return result(sources.todos_list(limit=limit, cursor=cursor))


def score_conversations(limit=5):
    rows, info = bf.fetch_report_data(limit=limit, persist=False)
    return result(
        [
            {
                "title": row["Session_Title"],
                "date": str(row.get("Recording_Date") or ""),
                "engagement": row["Engagement_Level"],
                "forward_motion": row["Forward_Motion"],
                "tone": row["Tone_Rating"],
            }
            for row in rows
        ],
        detail=info["detail"],
        interpretation="Heuristic observations about conversation structure, not objective judgments about people.",
    )


def generate_report(limit=10):
    from .reports import generate

    with WRITE_LOCK:
        return generate(limit=limit)


def bee_diary(limit=3):
    from .bee_persona import run_persona

    if not DEMO:
        run("me", timeout=10)
    with WRITE_LOCK:
        path = Path(run_persona(limit=limit))
        return result(path.read_text(encoding="utf-8"), file=str(path))


def user_profile(refresh=False, full=False, limit=50):
    from .profile import run_profile

    if full and not refresh:
        raise BeeError(
            "A full rebuild requires refresh=true. Otherwise the saved profile is read without changes."
        )
    path = DATA_DIR / "user.md"
    with WRITE_LOCK:
        if refresh:
            if not DEMO:
                run("me", timeout=10)
            filename, info = run_profile(full=full, limit=limit)
            path = Path(filename)
        else:
            info = {}
        if not path.is_file():
            return result(
                None,
                message="No saved profile yet. Call user_profile with refresh=true to build it.",
            )
        return result(path.read_text(encoding="utf-8"), file=str(path), update=info)
