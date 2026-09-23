"""Bounded, read-only Bee CLI access. No shell and no silent demo fallback."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .config import DATA_DIR, DEMO, LLM_ENABLED


class BeeError(RuntimeError):
    """An actionable error safe to return to an MCP client."""


def command() -> list[str]:
    name = os.getenv("BEE_CLI", "bee")
    executable = (
        str(Path(name).resolve())
        if os.getenv("BEE_CLI") and Path(name).is_file()
        else shutil.which(name)
    )
    if not executable:
        raise BeeError(
            "Bee CLI not found. Install it with npm install -g @beeai/cli, then run bee login. Use beeplex --demo for sample data."
        )
    path = Path(executable)
    # The repository simulator is a Python script, including on Windows.
    if path.suffix == ".py":
        return [sys.executable, str(path)]
    if path.name == "bee":
        with path.open("rb") as handle:
            if handle.read(24).startswith(b"#!/usr/bin/env python"):
                return [sys.executable, str(path)]
    if path.suffix.lower() in {".cmd", ".bat"}:
        # npm shims invoke a batch shell on Windows. Launch their JS entry
        # point directly so search text and ids can never become shell code.
        package = path.parent / "node_modules" / "@beeai" / "cli"
        node = shutil.which("node")
        try:
            manifest = json.loads(
                (package / "package.json").read_text(encoding="utf-8")
            )
            entry = manifest["bin"]
            entry = entry["bee"] if isinstance(entry, dict) else entry
            script = (package / entry).resolve()
            script.relative_to(package.resolve())
        except (OSError, ValueError, KeyError, TypeError):
            raise BeeError(
                "Cannot resolve the Bee npm launcher. Reinstall @beeai/cli or set BEE_CLI to its executable."
            ) from None
        if not node or not script.is_file():
            raise BeeError(
                "Bee requires Node.js on PATH and an installed @beeai/cli package."
            )
        return [node, str(script)]
    return [str(path)]


def run(*args: str, timeout: int = 60):
    argv = command() + list(args)
    if "--json" not in args:
        argv.append("--json")
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        raise BeeError(
            f"Bee did not respond within {timeout} seconds. Try again or check bee me."
        ) from None
    except OSError:
        raise BeeError(
            "Bee could not start. Check BEE_CLI and your Bee CLI installation."
        ) from None
    if result.returncode:
        # CLI stderr can include personal data or credentials; don't echo it.
        raise BeeError(
            "Bee could not complete the request. Run bee me to check your login; run bee login if needed."
        )
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise BeeError(
            "Bee returned invalid JSON. Check or update the Bee CLI."
        ) from None
    if not isinstance(payload, (dict, list)):
        raise BeeError(
            "Bee returned an unexpected response; expected a JSON object or list."
        )
    return payload


def status() -> dict:
    result = {
        "mode": "demo" if DEMO else "live",
        "connected": True,
        "data_dir": str(DATA_DIR),
        "llm_enabled": LLM_ENABLED,
    }
    if DEMO:
        result["detail"] = (
            "Sample memories only. These are not the user's real conversations."
        )
        return result
    try:
        run("me", timeout=10)
        result["detail"] = "Bee CLI is connected."
    except BeeError as exc:
        result.update(connected=False, detail=str(exc))
    return result
