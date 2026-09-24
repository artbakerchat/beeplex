"""Exercise direct commands through the installed entry point without Bee access."""

import json
from datetime import date
import os
from pathlib import Path
import subprocess
import sys

import pytest


COMMANDS = [
    (["status"], {"connected", "detail", "data_dir"}),
    (["context"], {"data", "window", "has_more"}),
    (["search", "launch"], {"data", "date_timezone"}),
    (["conversations"], {"data", "next_cursor"}),
    (["read", "mock-conv-1"], {"data", "next_offset", "total_utterances"}),
    (["todos"], {"data"}),
    (["score"], {"data", "detail", "interpretation"}),
    (["report", "--limit", "1"], {"files", "count"}),
    (["diary", "--limit", "1"], {"data", "file"}),
    (["profile"], {"data", "message"}),
    (
        ["doctor"],
        {"bee_cli_installed", "logged_in", "reports_installed", "data_dir_writable"},
    ),
]


def run_cli(tmp_path, *args, demo=True, **env):
    """Use isolated output and a deliberately unavailable live CLI."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "beeplex",
            *(["--demo"] if demo else []),
            "--data-dir",
            str(tmp_path / "output"),
            *args,
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "BEEPLEX_DEMO": "0",
            "BEEPLEX_LLM": "0",
            "BEE_CLI": "beeplex-missing-command",
            **env,
        },
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("args,keys", COMMANDS)
@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("env_demo", [False, True])
def test_demo_commands(tmp_path, args, keys, as_json, env_demo):
    response = run_cli(
        tmp_path,
        *args,
        *(["--json"] if as_json else []),
        demo=not env_demo,
        BEEPLEX_DEMO="1" if env_demo else "0",
    )
    assert response.returncode == 0, response.stderr
    if as_json:
        payload = json.loads(response.stdout)
        assert payload["mode"] == "demo"
        assert keys <= payload.keys()
        if args[0] == "report":
            assert payload["count"] == 1
            assert all(Path(path).is_file() for path in payload["files"])
        if args[0] == "doctor":
            assert payload["logged_in"] is None
            assert payload["data_dir_writable"]
    else:
        assert "Mode: demo (sample memories)" in response.stdout
        assert not response.stdout.startswith("{")


def test_arguments_and_pagination(tmp_path):
    first = run_cli(tmp_path, "conversations", "--limit", "1", "--json")
    payload = json.loads(first.stdout)
    assert len(payload["data"]) == 1
    second = run_cli(
        tmp_path,
        "conversations",
        "--limit",
        "1",
        "--cursor",
        payload["next_cursor"],
        "--json",
    )
    assert json.loads(second.stdout)["data"][0]["id"] != payload["data"][0]["id"]
    read = run_cli(
        tmp_path, "read", "mock-conv-1", "--offset", "1", "--limit", "1", "--json"
    )
    assert json.loads(read.stdout)["data"]["utterances"][0]["speaker"] == "Priya"
    search = run_cli(
        tmp_path,
        "search",
        "launch",
        "--semantic",
        "--since",
        "1999-01-01",
        "--until",
        "2000-01-01",
        "--limit",
        "1",
        "--json",
    )
    assert json.loads(search.stdout)["data"]["results"] == []
    context = run_cli(
        tmp_path,
        "context",
        "--period",
        "date",
        "--date-str",
        date.today().isoformat(),
        "--json",
    )
    assert context.returncode == 0, context.stderr
    profile = run_cli(
        tmp_path, "profile", "--refresh", "--full", "--limit", "1", "--json"
    )
    assert profile.returncode == 0, profile.stderr
    assert Path(json.loads(profile.stdout)["file"]).is_file()


@pytest.mark.parametrize(
    "args",
    [
        ["context", "--period", "date"],
        ["search", "launch", "--since", "2026-02-30"],
        ["read", "mock-conv-1", "--offset", "-1"],
        ["read", "missing"],
        ["score", "--limit", "51"],
        ["profile", "--full"],
    ],
)
def test_invalid_arguments(tmp_path, args):
    response = run_cli(tmp_path, *args, "--json")
    assert response.returncode != 0
    assert response.stderr
    assert "Traceback" not in response.stderr
    assert not response.stdout


def test_legacy_flags(tmp_path):
    check = run_cli(tmp_path, "--check")
    assert check.returncode == 0
    assert json.loads(check.stdout)["connected"]
    disconnected = run_cli(tmp_path, "--check", demo=False)
    assert disconnected.returncode == 1
    assert not json.loads(disconnected.stdout)["connected"]
    config = run_cli(tmp_path, "--config")
    assert config.returncode == 0
    assert json.loads(config.stdout)["mcpServers"]["beeplex"]["args"] == [
        "-m",
        "beeplex",
        "--demo",
        "--data-dir",
        str(tmp_path / "output"),
    ]


def test_flags_after_command_and_doctor_failures(tmp_path):
    response = run_cli(
        tmp_path,
        "status",
        "--demo",
        "--data-dir",
        str(tmp_path / "other"),
        "--json",
        demo=False,
    )
    assert response.returncode == 0
    assert json.loads(response.stdout)["data_dir"] == str(tmp_path / "other" / "demo")
    (tmp_path / "output").write_text("a file blocks the directory")
    response = run_cli(tmp_path, "doctor", "--json", demo=False)
    assert response.returncode == 0
    payload = json.loads(response.stdout)
    assert not payload["bee_cli_installed"]
    assert not payload["logged_in"]
    assert not payload["data_dir_writable"]
    assert payload["cli_error"]
