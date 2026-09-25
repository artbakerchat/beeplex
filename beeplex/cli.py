"""Direct shell access to the same functions registered as MCP tools."""

import argparse
from contextlib import redirect_stdout
from importlib.util import find_spec
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryFile
from typing import Any


# Function names and defaults mirror server.py; imports wait for environment setup.
COMMANDS = {
    "status": ("connection_status", None, "Check the Bee connection."),
    "context": ("get_context", 10, "Catch up on recent or dated memories."),
    "search": ("search_memories", 10, "Search memories for a topic or phrase."),
    "conversations": ("fetch_conversations", 5, "Browse recent conversations."),
    "read": ("read_conversation", 50, "Read a conversation transcript."),
    "voice": (None, None, "Open a browser transcript voice editor."),
    "todos": ("get_todos", 20, "List commitments and action items."),
    "score": ("score_conversations", 5, "Score recent conversations."),
    "report": ("generate_report", 10, "Export Office reports and a dashboard."),
    "diary": ("bee_diary", 3, "Write today's diary."),
    "profile": ("user_profile", 50, "Read or refresh the saved profile."),
    "doctor": (None, None, "Diagnose local setup."),
}


def add_subcommands(parser: argparse.ArgumentParser) -> None:
    """Add direct commands without importing process configuration or MCP."""
    commands = parser.add_subparsers(dest="command")
    for name, (_, limit, description) in COMMANDS.items():
        sub = commands.add_parser(name, help=description, description=description)
        sub.add_argument(
            "--json", action="store_true", help="Print the full JSON payload."
        )
        # SUPPRESS preserves global values when these flags precede the command.
        sub.add_argument(
            "--demo",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Use sample memories without a Bee login.",
        )
        sub.add_argument(
            "--data-dir",
            default=argparse.SUPPRESS,
            help="Folder for reports, diary and profile.",
        )
        if limit is not None:
            sub.add_argument(
                "--limit",
                type=int,
                default=limit,
                choices=range(1, 51),
                metavar="1..50",
            )
        if name == "voice":
            sub.add_argument("conversation_id")
        if name == "context":
            sub.add_argument(
                "--period", choices=("recent", "today", "date"), default="recent"
            )
            sub.add_argument("--date-str", help="Calendar date, YYYY-MM-DD.")
        elif name == "search":
            sub.add_argument("query", help="Topic or phrase to find.")
            sub.add_argument("--since", help="First calendar day, YYYY-MM-DD.")
            sub.add_argument("--until", help="Last calendar day, YYYY-MM-DD.")
            sub.add_argument("--semantic", action="store_true")
        elif name == "read":
            sub.add_argument("conversation_id")
            sub.add_argument("--offset", type=int, default=0)
        elif name in {"conversations", "todos"}:
            sub.add_argument("--cursor")
        elif name == "profile":
            sub.add_argument("--refresh", action="store_true")
            sub.add_argument("--full", action="store_true")


def doctor() -> dict[str, Any]:
    """Check setup, probing writes at the nearest existing data directory ancestor."""
    from .client import BeeError, command, status
    from .config import DATA_DIR, DEMO

    result = status()
    name = os.getenv("BEE_CLI", "bee")
    result["bee_cli_installed"] = (
        bool(shutil.which("bee"))
        if DEMO
        else bool(shutil.which(name) or Path(name).is_file())
    )
    try:
        result["active_cli"] = command()
    except BeeError as exc:
        result["active_cli"] = None
        result["cli_error"] = str(exc)
    # Sample data cannot tell us whether a real account is authenticated.
    result["logged_in"] = None if DEMO else result["connected"]
    result["reports_installed"] = all(
        find_spec(module) is not None for module in ("docx", "openpyxl", "pptx")
    )
    probe = DATA_DIR
    try:
        while not probe.exists():
            probe = probe.parent
        with TemporaryFile(dir=probe) as handle:
            handle.write(b"beeplex write check")
            handle.flush()
        result["data_dir_writable"] = True
    except OSError as exc:
        result["data_dir_writable"] = False
        result["data_dir_error"] = str(exc)
    return result


def _human(value: Any, indent: str = "") -> list[str]:
    """Render nested tool data as readable text, retaining IDs and pagination."""
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if item is None:
                continue
            label = key.replace("_", " ").capitalize()
            if isinstance(item, (dict, list)):
                lines.append(f"{indent}{label}:")
                lines.extend(_human(item, indent + "  "))
            else:
                lines.append(f"{indent}{label}: {_short(item)}")
        return lines
    if isinstance(value, list):
        return [line for item in value for line in _human(item, indent)] or [
            f"{indent}No items found."
        ]
    return [f"{indent}{_short(value)}"]


def _short(value: Any) -> str:
    """Keep summaries compact; JSON retains the complete text."""
    text = " ".join(str(value).split())
    return text if len(text) <= 300 else text[:297] + "..."


def dispatch(args: argparse.Namespace) -> int:
    """Call a registered function directly, preserving its full JSON result."""
    from pydantic import ValidationError, validate_call

    from . import server
    from .client import BeeError

    kwargs = {
        key: value
        for key, value in vars(args).items()
        if key not in {"command", "json", "demo", "data_dir", "check", "config"}
    }
    try:
        # Keep any library progress output off the machine-readable stdout stream.
        with redirect_stdout(sys.stderr):
            if args.command == "doctor":
                payload = doctor()
            elif args.command == "voice":
                from .voice_editor import create_aggregate, create_editor

                from . import bee_fetcher

                conversation = bee_fetcher.get_conversation(args.conversation_id)
                if not conversation:
                    raise BeeError(f"Conversation not found: {args.conversation_id}")
                payload = create_editor(conversation)
                # Refresh the multi-scenario page covering every recording in
                # this mode (live Bee CLI or demo), next to the single page.
                try:
                    summaries = bee_fetcher.list_conversations(limit=50)
                    full = []
                    for summary in summaries:
                        conv = bee_fetcher.get_conversation(
                            bee_fetcher._conv_id(summary) or ""
                        )
                        if conv:
                            full.append(conv)
                    payload["aggregate"] = create_aggregate(full)
                except BeeError as exc:
                    payload["aggregate"] = {
                        "path": None,
                        "scenarios": 0,
                        "error": str(exc),
                    }
            else:
                function = getattr(server, COMMANDS[args.command][0])
                # Direct calls bypass MCP's validation; reuse the tool annotations.
                payload = validate_call(function)(**kwargs)
    except (BeeError, OSError, ValidationError) as exc:
        print(f"beeplex: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, indent=2))
    elif args.command == "doctor":
        print(
            f"Mode: {payload['mode']}"
            + (" (sample memories)" if payload["mode"] == "demo" else "")
        )
        print(f"Bee CLI installed: {'yes' if payload['bee_cli_installed'] else 'no'}")
        login = payload["logged_in"]
        print(
            f"Logged in: {'not checked in demo mode' if login is None else ('yes' if login else 'no')}"
        )
        print(
            f"Reports extras installed: {'yes' if payload['reports_installed'] else 'no'}"
        )
        print(f"Data directory: {payload['data_dir']}")
        print(
            f"Data directory writable: {'yes' if payload['data_dir_writable'] else 'no'}"
        )
        print(payload["detail"])
        for key in ("cli_error", "data_dir_error"):
            if key in payload:
                print(payload[key])
    elif args.command == "voice":
        print(f"Browser transcript editor: {payload['path']}")
        aggregate = payload.get("aggregate") or {}
        if aggregate.get("path"):
            print(
                f"All-recordings editor: {aggregate['path']}"
                f" ({aggregate['scenarios']} recordings)"
            )
        elif aggregate.get("error"):
            print(f"All-recordings editor skipped: {aggregate['error']}")
        print("Open this HTML file in your browser. Audio uses browser text-to-speech.")
    else:
        print(
            f"Mode: {payload['mode']}"
            + (" (sample memories)" if payload["mode"] == "demo" else "")
        )
        print(
            "\n".join(
                _human({key: value for key, value in payload.items() if key != "mode"})
            )
        )
    return 0
