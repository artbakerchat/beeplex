"""Local UI routes stay on loopback and expose only known actions."""

from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json

import pytest

from python import server as mcp_server
from python.web_ui import LocalHTTPServer, perform_action


@pytest.fixture
def ui_server():
    server = LocalHTTPServer(("127.0.0.1", 0), "test-token")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_home_page_contains_local_interface_and_token(ui_server):
    url, _ = ui_server
    with urlopen(url) as response:
        page = response.read().decode("utf-8")

    assert response.status == 200
    assert "BeePlex | Memory desk" in page
    assert 'const token = "test-token"' in page
    assert "127.0.0.1" not in page


def test_action_endpoint_requires_token(ui_server):
    url, _ = ui_server
    request = Request(
        f"{url}/api/action",
        data=json.dumps({"action": "status", "params": {}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with pytest.raises(HTTPError) as error:
        urlopen(request)

    assert error.value.code == 403


def test_action_endpoint_calls_allowlisted_tool(ui_server, monkeypatch):
    url, _ = ui_server

    def fake_status():
        return {"connected": True}

    monkeypatch.setattr(mcp_server, "connection_status", fake_status)
    request = Request(
        f"{url}/api/action",
        data=json.dumps({"action": "status", "params": {}}).encode(),
        headers={
            "Content-Type": "application/json",
            "X-BeePlex-Token": "test-token",
        },
        method="POST",
    )

    with urlopen(request) as response:
        payload = json.loads(response.read())

    assert payload == {"connected": True}


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError, match="Unknown BeePlex action"):
        perform_action("arbitrary", {})