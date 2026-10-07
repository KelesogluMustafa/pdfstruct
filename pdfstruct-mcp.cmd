@echo off
rem Local MCP server (stdio) without activating the venv. Used by Claude Code / Claude Desktop.
"%~dp0.venv\Scripts\python.exe" -m pdfstruct.mcp_server %*
