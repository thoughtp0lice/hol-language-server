"""End-to-end tests of the language server over stdio, speaking LSP."""

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

from hol_server_paths import PROJECT

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lsp_server.py")
TACTICS = os.path.join(PROJECT, "tactics.ml")


def uri(path: str) -> str:
    return "file://" + path


class LspClient:
    """Minimal JSON-RPC client over Content-Length framing."""

    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        assert proc.stdin is not None and proc.stdout is not None
        self.stdin = proc.stdin
        self.stdout = proc.stdout
        self.next_id = 0
        # Server notifications (no id) seen while waiting for responses.
        self.notifications: list[dict[str, Any]] = []

    def _read_message(self) -> dict[str, Any]:
        headers: dict[str, str] = {}
        while True:
            line = self.stdout.readline().decode("ascii")
            if line in ("\r\n", ""):
                break
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        body = self.stdout.read(int(headers["content-length"]))
        return json.loads(body)

    def _send(self, message: dict[str, Any]) -> None:
        body = json.dumps(message).encode("utf-8")
        self.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.stdin.flush()

    def call(self, method: str, params: object) -> dict[str, Any]:
        """The response message, result or error."""
        self.next_id += 1
        self._send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        while True:
            message = self._read_message()
            if "id" not in message:
                self.notifications.append(message)
            elif message["id"] == self.next_id:
                return message

    def request(self, method: str, params: object) -> Any:
        message = self.call(method, params)
        assert "error" not in message, message["error"]
        return message["result"]

    def warnings(self) -> list[str]:
        return [n["params"]["message"] for n in self.notifications
                if n["method"] == "window/showMessage" and n["params"]["type"] == 2]

    def notify(self, method: str, params: object) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})


def start_server(hol: str) -> Iterator[tuple[LspClient, Any]]:
    proc = subprocess.Popen(
        [sys.executable, SERVER, "--hol-path", hol, "--workspace", PROJECT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    client = LspClient(proc)
    try:
        result = client.request(
            "initialize",
            {
                "processId": None,
                "rootUri": None,
                "capabilities": {},
                "workspaceFolders": None,
            },
        )
        client.notify("initialized", {})
        yield client, result
    finally:
        try:
            client.request("shutdown", None)
        except Exception:
            pass
        client.notify("exit", None)
        client.stdin.close()
        proc.wait(timeout=30)


def test_initialize_advertises_the_subset():
    from hol_server_paths import HOL

    for _, result in start_server(HOL):
        capabilities = result["capabilities"]
        assert capabilities["hoverProvider"] is True
        assert capabilities["definitionProvider"] is True
        assert capabilities["documentSymbolProvider"] is True
        assert capabilities["workspaceSymbolProvider"] == {"resolveProvider": False}


def test_hover_definition_and_symbols():
    from hol_server_paths import HOL

    for client, _ in start_server(HOL):
        with open(TACTICS, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(TACTICS), "languageId": "ocaml", "version": 1, "text": text}},
        )
        hover = client.request(
            "textDocument/hover",
            {"textDocument": {"uri": uri(TACTICS)}, "position": {"line": 6, "character": 20}},
        )
        assert hover["contents"]["value"] == (
            "Theorem `ADD_SYM_ALT`\n```\n`|- !m n. n + m = m + n`\n```"
        )

        [target] = client.request(
            "textDocument/definition",
            {"textDocument": {"uri": uri(TACTICS)}, "position": {"line": 5, "character": 5}},
        )
        assert target["uri"] == uri(TACTICS)
        assert (target["range"]["start"]["line"], target["range"]["start"]["character"]) == (5, 4)

        symbols = client.request(
            "textDocument/documentSymbol", {"textDocument": {"uri": uri(TACTICS)}}
        )
        assert {s["name"] for s in symbols} >= {"HELPER_TAC", "MY_TAC", "OTHER_TAC"}

        found = client.request("workspace/symbol", {"query": "helper"})
        assert [s["name"] for s in found] == ["HELPER_TAC"]

        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(TACTICS)}})


def test_bad_settings_fail_initialize():
    proc = subprocess.Popen(
        [sys.executable, SERVER, "--workspace", PROJECT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={k: v for k, v in os.environ.items() if k != "HOL_LIGHT_DIR"},
    )
    client = LspClient(proc)
    try:
        for options, message in [
            ({"hol-light": {"holPath": "/hol"}}, "Unknown hol-light settings: holPath"),
            ({}, "No HOL Light directory"),
        ]:
            response = client.call(
                "initialize",
                {"processId": None, "rootUri": None, "capabilities": {},
                 "initializationOptions": options},
            )
            assert message in response["error"]["message"]
    finally:
        proc.kill()
        proc.wait(timeout=30)


def test_unresolved_loads_are_shown():
    from hol_server_paths import HOL

    main = os.path.join(PROJECT, "main.ml")
    for client, _ in start_server(HOL):
        with open(main, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(main), "languageId": "ocaml", "version": 1, "text": text}},
        )
        client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri(main)}})
        assert client.warnings() == [
            "Loads not found in the workspace: missing.ml",
            f"{main}: loads not found: missing.ml",
        ]
