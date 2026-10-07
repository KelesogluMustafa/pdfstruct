#!/usr/bin/env python3
"""Check an installed PDFStruct runtime before it is made the active one.

Run it with the Python of that runtime:

    <runtime>\\Scripts\\python.exe verify_runtime.py --expect 0.2.1

Checks, in order: the package (version, not editable, loaded from inside the runtime), the
command line (version and one real conversion), and the MCP server over stdio (initialize,
tools/list, two tools/call, and that stdout carries nothing but protocol messages).
Prints one line per check and exits 0 only when all pass. It reads no user documents.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

TOOLS = ["convert", "inspect", "read_excerpt", "search", "supported_formats"]
MARKER = "VERIFY-RUNTIME-MARKER-7391"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Failed(Exception):
    pass


def scripts_dir() -> Path:
    return Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")


def script(name: str) -> Path:
    path = scripts_dir() / (name + (".exe" if os.name == "nt" else ""))
    if not path.is_file():
        raise Failed(f"missing {path}")
    return path


def check_package(expect: str | None) -> str:
    from importlib import metadata

    import pdfstruct

    version = pdfstruct.__version__
    if expect and version != expect:
        raise Failed(f"installed version is {version}, expected {expect}")
    if metadata.version("pdfstruct") != version:
        raise Failed("package metadata and module version differ")
    direct = metadata.distribution("pdfstruct").read_text("direct_url.json")
    if direct and json.loads(direct).get("dir_info", {}).get("editable"):
        raise Failed("the install is editable (linked to a source folder)")
    module = Path(pdfstruct.__file__).resolve()
    if Path(sys.prefix).resolve() not in module.parents:
        raise Failed(f"pdfstruct is loaded from outside the runtime: {module}")
    return version


def check_cli(version: str, work: Path) -> None:
    done = subprocess.run([str(script("pdfstruct")), "--version"], capture_output=True, text=True,
                          timeout=120, creationflags=NO_WINDOW)
    if done.returncode != 0 or done.stdout.strip() != f"pdfstruct {version}":
        raise Failed(f"pdfstruct --version: exit {done.returncode}, {done.stdout.strip()!r}")
    source = work / "cli check.txt"
    source.write_text(MARKER + "\n", encoding="utf-8")
    done = subprocess.run([str(script("pdfstruct")), str(source), "--format", "json,md"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300, creationflags=NO_WINDOW)
    written = work / "output" / "cli check.txt.md"
    if done.returncode != 0 or not written.is_file() or MARKER not in written.read_text(encoding="utf-8"):
        raise Failed(f"command-line conversion failed (exit {done.returncode})")


class Server:
    """The MCP server process, driven with newline-delimited JSON-RPC as a client would."""

    def __init__(self, exe: Path):
        self.proc = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        self.lines: queue.Queue = queue.Queue()
        self.stdout_lines = 0
        self.stderr = b""
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        for raw in self.proc.stdout:
            self.lines.put(raw)
        self.lines.put(None)

    def _read_stderr(self) -> None:
        self.stderr = self.proc.stderr.read()

    def send(self, message: dict) -> None:
        self.proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def request(self, number: int, method: str, params: dict | None = None, timeout: int = 300) -> dict:
        self.send({"jsonrpc": "2.0", "id": number, "method": method, **({"params": params} if params else {})})
        while True:
            try:
                raw = self.lines.get(timeout=timeout)
            except queue.Empty:
                raise Failed(f"no answer to {method} within {timeout} s") from None
            if raw is None:
                raise Failed(f"the server closed its output before answering {method}")
            if not raw.strip():
                continue
            self.stdout_lines += 1
            try:
                message = json.loads(raw.decode("utf-8"))
            except ValueError:
                raise Failed(f"stdout is not clean JSON-RPC: {raw[:120]!r}") from None
            if message.get("jsonrpc") != "2.0":
                raise Failed(f"stdout carries a non-protocol message: {raw[:120]!r}")
            if message.get("id") == number:
                if "error" in message:
                    raise Failed(f"{method} returned an error: {message['error']}")
                return message["result"]

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=20)
        except Exception:
            self.proc.kill()


def tool_json(result: dict) -> dict:
    content = result.get("content") or []
    if result.get("isError") or len(content) != 1 or content[0].get("type") != "text":
        raise Failed(f"unexpected tool result shape: {str(result)[:200]}")
    return json.loads(content[0]["text"])


def check_mcp(version: str, work: Path) -> str:
    server = Server(script("pdfstruct-mcp"))
    try:
        init = server.request(1, "initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "pdfstruct-verify", "version": "1"}})
        info = init.get("serverInfo") or {}
        if info.get("name") != "pdfstruct" or info.get("version") != version:
            raise Failed(f"serverInfo is {info}")
        if "tools" not in (init.get("capabilities") or {}):
            raise Failed("the server does not announce tools")
        server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = sorted(tool["name"] for tool in server.request(2, "tools/list")["tools"])
        if tools != TOOLS:
            raise Failed(f"tools are {tools}")
        formats = tool_json(server.request(3, "tools/call", {"name": "supported_formats", "arguments": {}}))
        if formats.get("outputs", [])[-1:] != ["pdf"] or formats.get("version") != version:
            raise Failed("supported_formats answered unexpectedly")
        source = work / "mcp check.txt"
        source.write_text(MARKER + " " + "filler " * 200, encoding="utf-8")
        raw = server.request(4, "tools/call", {"name": "convert", "arguments": {
            "paths": [str(source)], "formats": ["json", "md"]}})
        text = raw["content"][0]["text"]
        answer = tool_json(raw)
        if not answer.get("ok") or answer["files"][0]["outputs"].get("md") != "mcp check.txt.md":
            raise Failed(f"convert answered: {text[:200]}")
        if MARKER in text or len(text) > 2000:
            raise Failed("the convert answer is not compact or carries document text")
        if not (work / "output" / "mcp check.txt.md").is_file():
            raise Failed("convert did not write its output file")
    finally:
        server.close()
    return f"{server.stdout_lines} protocol lines on stdout, {len(server.stderr)} bytes on stderr"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--expect", help="version this runtime must have")
    args = parser.parse_args()
    version = None
    with tempfile.TemporaryDirectory(prefix="pdfstruct_verify_") as tmp:
        for label, step in (("IMPORT", lambda: check_package(args.expect)),
                            ("CLI", lambda: check_cli(version, Path(tmp))),
                            ("MCP", lambda: check_mcp(version, Path(tmp)))):
            try:
                detail = step()
            except Failed as exc:
                print(f"{label}: FAIL - {exc}")
                return 1
            except Exception as exc:  # anything unexpected is a failed check, not a crash
                print(f"{label}: FAIL - {type(exc).__name__}: {exc}")
                return 1
            if label == "IMPORT":
                version = detail
            print(f"{label}: PASS" + (f" ({detail})" if detail else ""))
    print(f"RUNTIME OK: pdfstruct {version} at {sys.prefix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
