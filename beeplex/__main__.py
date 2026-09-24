"""One entry point: beeplex (or python -m beeplex)."""

import argparse
import json
import os
from pathlib import Path
import sys

from .cli import add_subcommands, dispatch


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Access Bee memories directly or through MCP (stdio)."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use clearly labelled sample memories; no Bee login required.",
    )
    parser.add_argument(
        "--data-dir",
        help="Folder for reports, diary and profile (default: ~/.beeplex).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Print connection diagnostics and exit; does not start MCP.",
    )
    mode.add_argument(
        "--config",
        action="store_true",
        help="Print ready-to-paste MCP client configuration and exit.",
    )
    add_subcommands(parser)
    args = parser.parse_args()
    if args.command and (args.check or args.config):
        parser.error("--check and --config cannot be combined with a subcommand")
    if args.demo or os.getenv("BEEPLEX_DEMO") == "1":
        os.environ["BEEPLEX_DEMO"] = "1"
        # Demo is a fake CLI on the same subprocess path as the real one, not
        # a code branch. Forcing BEE_CLI keeps the demo honest even if the
        # caller (e.g. a test harness) set BEE_CLI to something else.
        os.environ["BEE_CLI"] = str(Path(__file__).with_name("demo_cli.py"))
    if args.data_dir:
        os.environ["BEEPLEX_DATA_DIR"] = args.data_dir

    if args.config:
        server_args = ["-m", "beeplex"]
        if args.demo:
            server_args.append("--demo")
        if args.data_dir:
            server_args += [
                "--data-dir",
                str(Path(args.data_dir).expanduser().resolve()),
            ]
        print(
            json.dumps(
                {
                    "mcpServers": {
                        "beeplex": {"command": sys.executable, "args": server_args}
                    }
                },
                indent=2,
            )
        )
        return

    if args.check:
        from .client import status

        result = status()
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["connected"] else 1)

    if args.command:
        raise SystemExit(dispatch(args))

    from .server import server

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
