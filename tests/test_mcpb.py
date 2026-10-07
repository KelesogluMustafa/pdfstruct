"""Claude Desktop bundle (.mcpb): a thin Node connector to the installed pdfstruct-mcp."""
import asyncio
import json
import os
import shutil
import sys
import sysconfig
from pathlib import Path

import pytest

import pdfstruct
from conftest import TOOL_DIR

BUNDLE = TOOL_DIR / "integrations" / "claude-desktop"


def test_manifest_matches_the_package():
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "0.4" and manifest["name"] == "pdfstruct"
    assert manifest["version"] == pdfstruct.__version__  # bumped together with the package
    server = manifest["server"]
    assert server["type"] == "node" and (BUNDLE / server["entry_point"]).is_file()
    assert server["mcp_config"]["command"] == "node"
    assert sorted(tool["name"] for tool in manifest["tools"]) == [
        "convert", "inspect", "read_excerpt", "search", "supported_formats"]
    files = sorted(p.relative_to(BUNDLE).as_posix() for p in BUNDLE.rglob("*") if p.is_file())
    assert files == ["manifest.json", "server/index.js"]  # a connector only: no engine, no models
    launcher = (BUNDLE / "server" / "index.js").read_text(encoding="utf-8")
    assert "shell: true" not in launcher and "exec(" not in launcher  # never through a shell


def test_launcher_bridges_stdio_to_the_installed_server():
    mcp = pytest.importorskip("mcp")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    from mcp.client.stdio import StdioServerParameters

    script = Path(sysconfig.get_path("scripts")) / ("pdfstruct-mcp" + (".exe" if os.name == "nt" else ""))
    assert script.is_file(), "pdfstruct-mcp entry point missing"

    async def scenario():
        env = dict(os.environ, PDFSTRUCT_MCP_COMMAND=str(script))
        params = StdioServerParameters(command=node, args=[str(BUNDLE / "server" / "index.js")], env=env)
        async with mcp.Client(params) as client:
            tools = sorted(tool.name for tool in (await client.list_tools()).tools)
            answer = await client.call_tool("supported_formats", {})
            return tools, json.loads(answer.content[0].text)

    tools, formats = asyncio.run(scenario())
    assert tools == ["convert", "inspect", "read_excerpt", "search", "supported_formats"]
    assert formats["outputs"][-1] == "pdf"
