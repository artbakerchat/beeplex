"""Exercise the actual installed entry point over MCP stdio, without an account."""

import asyncio
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters
import pytest

ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def connect(tmp_path, *, demo=False, protocol="auto", **env):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "beeplex"] + (["--demo"] if demo else []),
        cwd=str(tmp_path),
        env={
            "BEE_CLI": str(ROOT / "simulator" / "bee"),
            "BEEPLEX_DATA_DIR": str(tmp_path / "output"),
            "BEEPLEX_DEMO": "0",
            "BEEPLEX_LLM": "0",
            "SIM_BEE_EMPTY": "0",
            "SIM_BEE_FAIL_AUTH": "0",
            **env,
        },
    )
    async with Client(params, mode=protocol, read_timeout_seconds=30) as client:
        yield client


async def call(client, name, **kwargs):
    response = await client.call_tool(name, kwargs)
    assert not response.is_error, response.content
    assert response.structured_content is not None
    return response.structured_content


@pytest.mark.parametrize(
    "demo,protocol", [(True, "auto"), (False, "auto"), (True, "legacy")]
)
def test_conversational_workflow(tmp_path, demo, protocol):
    async def scenario():
        async with connect(tmp_path, demo=demo, protocol=protocol) as client:
            catalog = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert set(catalog) == {
                "connection_status",
                "get_context",
                "search_memories",
                "fetch_conversations",
                "read_conversation",
                "get_todos",
                "score_conversations",
                "disagreement_view",
                "generate_report",
                "bee_diary",
                "user_profile",
            }
            assert catalog["fetch_conversations"].annotations.read_only_hint
            assert not catalog["generate_report"].annotations.read_only_hint
            schema = catalog["fetch_conversations"].input_schema
            assert schema["properties"]["limit"]["maximum"] == 50
            assert (await client.read_resource("beeplex://guide")).contents
            assert {p.name for p in (await client.list_prompts()).prompts} == {
                "catch_up",
                "reflect",
            }
            assert (await client.get_prompt("catch_up")).messages

            status = await call(client, "connection_status")
            assert status["connected"]
            assert status["mode"] == ("demo" if demo else "live")
            assert not status["llm_enabled"]
            assert (await call(client, "get_context"))["data"]
            assert (await call(client, "get_context", period="today"))["data"]
            assert (
                await call(
                    client,
                    "get_context",
                    period="date",
                    date_str=date.today().isoformat(),
                )
            )["data"]

            first = await call(client, "fetch_conversations", limit=1)
            assert len(first["data"]) == 1
            assert "utterances" not in first["data"][0]
            assert first["next_cursor"] is not None
            second = await call(
                client, "fetch_conversations", limit=1, cursor=first["next_cursor"]
            )
            assert first["data"][0]["id"] != second["data"][0]["id"]
            transcript = await call(
                client,
                "read_conversation",
                conversation_id=first["data"][0]["id"],
                limit=1,
            )
            assert len(transcript["data"]["utterances"]) == 1
            assert transcript["next_offset"] == 1
            following = await call(
                client,
                "read_conversation",
                conversation_id=first["data"][0]["id"],
                offset=1,
                limit=1,
            )
            assert following["data"]["utterances"] != transcript["data"]["utterances"]

            query = "launch" if demo else "the"
            found = await call(client, "search_memories", query=query, limit=1)
            assert len(found["data"]["results"]) <= 1
            old = await call(client, "search_memories", query=query, until="2000-01-01")
            assert old["data"]["results"] == []
            since = (date.today() - timedelta(days=3)).isoformat()
            assert (await call(client, "search_memories", query=query, since=since))[
                "data"
            ]["results"]
            assert (await call(client, "get_todos", limit=1))["data"]["todos"]
            scores = await call(client, "score_conversations", limit=1)
            assert len(scores["data"]) == 1
            assert scores["data"][0]["title"] == first["data"][0]["title"]
            assert (await call(client, "user_profile"))["data"] is None
            assert not (tmp_path / "output").exists(), (
                "Read tools must not create files"
            )

            report = await call(client, "generate_report", limit=1)
            assert report["count"] == 1
            assert len(report["files"]) == 4
            assert all(Path(name).is_file() for name in report["files"])
            repeated = await call(client, "generate_report", limit=1)
            assert repeated["files"] == report["files"], (
                "Replaced files must still be reported"
            )
            diary = await call(client, "bee_diary", limit=1)
            assert Path(diary["file"]).read_text(encoding="utf-8") == diary["data"]
            profile = await call(client, "user_profile", refresh=True, limit=1)
            assert Path(profile["file"]).is_file()
            assert (await call(client, "user_profile"))["data"] == profile["data"]
            if demo:
                assert (tmp_path / "output" / "demo" / "user.md").is_file()
                assert not (tmp_path / "output" / "user.md").exists()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "name,args",
    [
        ("fetch_conversations", {"limit": 0}),
        ("score_conversations", {"limit": 51}),
        ("read_conversation", {"conversation_id": "missing", "offset": -1}),
        ("read_conversation", {"conversation_id": "missing"}),
        ("search_memories", {"query": "   "}),
        ("search_memories", {"query": "launch", "since": "2026-02-30"}),
        (
            "search_memories",
            {"query": "launch", "since": "2026-09-23", "until": "2026-09-01"},
        ),
        ("get_context", {"period": "date"}),
        ("get_context", {"period": "date", "date_str": "2026-02-30"}),
        ("user_profile", {"full": True}),
    ],
)
def test_invalid_inputs_are_tool_errors(tmp_path, name, args):
    async def scenario():
        async with connect(tmp_path, demo=True) as client:
            response = await client.call_tool(name, args)
            assert response.is_error
            assert not (tmp_path / "output").exists()

    asyncio.run(scenario())


def test_empty_live_account(tmp_path):
    async def scenario():
        async with connect(tmp_path, SIM_BEE_EMPTY="1") as client:
            assert (await call(client, "fetch_conversations"))["data"] == []
            assert (await call(client, "score_conversations"))["data"] == []
            report = await call(client, "generate_report")
            assert report["count"] == 0 and report["files"] == []

    asyncio.run(scenario())


def test_all_simulator_conversations_score_without_writing(tmp_path):
    async def scenario():
        async with connect(tmp_path) as client:
            conversations = await call(client, "fetch_conversations", limit=50)
            scores = await call(client, "score_conversations", limit=50)
            assert len(scores["data"]) == len(conversations["data"]) == 9
            assert not (tmp_path / "output").exists()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "env", [{"SIM_BEE_FAIL_AUTH": "1"}, {"BEE_CLI": "beeplex-missing-command"}]
)
def test_disconnected_never_becomes_demo(tmp_path, env):
    async def scenario():
        async with connect(tmp_path, **env) as client:
            status = await call(client, "connection_status")
            assert status["mode"] == "live" and not status["connected"]
            assert "login" in status["detail"]
            response = await client.call_tool("fetch_conversations", {})
            assert response.is_error
            assert not (tmp_path / "output").exists()

    asyncio.run(scenario())
