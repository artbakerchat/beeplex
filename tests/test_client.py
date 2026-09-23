import json
from pathlib import Path
import subprocess
import sys

import pytest

from beeplex import client


@pytest.mark.parametrize("failure", ["timeout", "exit", "json", "shape"])
def test_cli_errors_are_actionable_and_do_not_leak_stderr(monkeypatch, failure):
    monkeypatch.setattr(client, "command", lambda: ["bee"])

    def fake_run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("bee", 1)
        return subprocess.CompletedProcess(
            args[0],
            1 if failure == "exit" else 0,
            "null" if failure == "shape" else "bad-json",
            "private transcript and token",
        )

    monkeypatch.setattr(client.subprocess, "run", fake_run)
    with pytest.raises(client.BeeError) as error:
        client.run("now", timeout=1)
    assert "private" not in str(error.value)
    assert str(error.value)


def test_search_text_is_an_argument_not_shell_code(monkeypatch):
    monkeypatch.setattr(client, "command", lambda: ["bee"])
    query = 'roadmap & echo secret | $(whoami) "quoted"'

    def fake_run(argv, **kwargs):
        assert argv == ["bee", "search", "--query", query, "--json"]
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 60
        return subprocess.CompletedProcess(argv, 0, '{"results": []}', "")

    monkeypatch.setattr(client.subprocess, "run", fake_run)
    assert client.run("search", "--query", query) == {"results": []}


def test_windows_npm_shim_launches_node_directly(tmp_path, monkeypatch):
    shim = tmp_path / "bee.cmd"
    shim.write_text("@echo off", encoding="utf-8")
    package = tmp_path / "node_modules" / "@beeai" / "cli"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"bin": {"bee": "cli.js"}}), encoding="utf-8"
    )
    (package / "cli.js").write_text("", encoding="utf-8")
    monkeypatch.setenv("BEE_CLI", str(shim))
    monkeypatch.setattr(client.shutil, "which", lambda name: "node.exe")
    assert client.command() == ["node.exe", str(package / "cli.js")]


def test_simulator_launches_on_windows_and_posix(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "simulator" / "bee"
    monkeypatch.setenv("BEE_CLI", str(path))
    assert client.command() == [sys.executable, str(path)]


def test_config_command_prints_usable_absolute_paths(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "beeplex", "--demo", "--config", "--data-dir", "output"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(proc.stdout)["mcpServers"]["beeplex"]
    assert config["command"] == sys.executable
    assert config["args"] == [
        "-m",
        "beeplex",
        "--demo",
        "--data-dir",
        str(tmp_path / "output"),
    ]
    assert not (tmp_path / "output").exists()
