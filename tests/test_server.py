"""End-to-end tests of the lookup MCP server over stdio."""

import asyncio
import json
import os
import subprocess
import sys
from typing import Any

from hol_server_paths import HOL, PROJECT
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent, Tool

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server.py")


async def run(calls: list[tuple[str, dict[str, Any]]]) -> tuple[list[Tool], list[CallToolResult]]:
    params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER, "--hol-path", HOL, "--workspace", PROJECT],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = (await client.list_tools()).tools
            results = []
            for name, args in calls:
                results.append(await client.call_tool(name, args))
            return tools, results


def check(result: CallToolResult) -> dict[str, Any]:
    assert not result.isError, result.content
    content = result.content[0]
    assert isinstance(content, TextContent)
    return json.loads(content.text)


def test_lists_only_the_definition_tool():
    [tools, _] = asyncio.run(run([]))
    assert [t.name for t in tools] == ["definition_source"]


def test_definition_source_follows_the_definitions_a_tactic_is_built_from():
    async def calls():
        params = StdioServerParameters(
            command=sys.executable,
            args=[SERVER, "--hol-path", HOL, "--workspace", PROJECT],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                helper = check(await client.call_tool("definition_source", {"name": "HELPER_TAC", "depth": 0}))
                other = check(await client.call_tool("definition_source", {"name": "OTHER_TAC", "depth": 2}))
                budgeted = check(
                    await client.call_tool(
                        "definition_source",
                        {"name": "OTHER_TAC", "depth": 2, "max_total_chars": 1},
                    )
                )
                cut = check(
                    await client.call_tool(
                        "definition_source", {"name": "HELPER_TAC", "max_chars": 25}
                    )
                )
                return helper, other, budgeted, cut

    helper, other, budgeted, cut = asyncio.run(calls())
    assert helper["definitions"] == [
        {
            "name": "HELPER_TAC",
            "kind": "value",
            "source": "let HELPER_TAC th =\n  REWRITE_TAC[th; ADD_SYM_ALT];;",
            # The parameter th is not the global th of line 3.
            # REWRITE_TAC has no indexed definition, so it is left out.
            "references": [
                {"name": "ADD_SYM_ALT", "kind": "theorem", "statement": "!m n. n + m = m + n"},
            ],
        }
    ]
    # Two items not separated by `;;`; names in strings and terms are not references.
    assert [(d["name"], d.get("via")) for d in other["definitions"]] == [
        ("OTHER_TAC", None),
        ("MY_TAC", "OTHER_TAC"),
        ("HELPER_TAC", "MY_TAC"),
    ]
    # Value-only references carry nothing beyond a name, so they are
    # left out; HELPER_TAC still arrives as an expanded definition.
    assert other["definitions"][1]["references"] == []
    assert budgeted["not_expanded"] == [{"name": "MY_TAC", "via": "OTHER_TAC"}]
    # A cut source lists only the names in the part returned.
    [cut_def] = cut["definitions"]
    assert (
        cut_def["source"],
        cut_def["truncated"],
        [r["name"] for r in cut_def["references"]],
    ) == ("let HELPER_TAC th =\n  REW", True, [])


def test_definition_source_defaults_to_depth_0():
    [_, [result]] = asyncio.run(
        run([("definition_source", {"name": "OTHER_TAC"})])
    )
    assert [(d["name"], d.get("via")) for d in check(result)["definitions"]] == [
        ("OTHER_TAC", None)
    ]


def test_definition_source_reports_byte_identical_definitions_once():
    [_, [result]] = asyncio.run(run([("definition_source", {"name": "DUP_TAC"})]))
    assert len(check(result)["definitions"]) == 1


def test_no_help_page_reaches_the_client():
    async def missing():
        params = StdioServerParameters(
            command=sys.executable,
            args=[SERVER, "--hol-path", HOL, "--workspace", PROJECT],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                # REWRITE_TAC is documented in HOL Light but has no indexed definition here.
                return await client.call_tool("definition_source", {"name": "REWRITE_TAC"})

    result = asyncio.run(missing())
    assert result.isError
    content = result.content[0]
    assert isinstance(content, TextContent)
    text = content.text
    assert "No definition of REWRITE_TAC is indexed" in text
    assert "Help" not in text


def test_unresolved_loads_are_reported():
    main = os.path.join(PROJECT, "main.ml")
    [_, [result]] = asyncio.run(run([("definition_source", {"name": "MY_THM", "file": main})]))
    assert check(result)["unresolved_loads"] == ["missing.ml"]


def test_server_refuses_to_start_without_hol_light():
    proc = subprocess.run(
        [sys.executable, SERVER, "--workspace", PROJECT],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        env={k: v for k, v in os.environ.items() if k != "HOL_LIGHT_DIR"},
    )
    assert proc.returncode != 0
    assert "No HOL Light directory" in proc.stderr
