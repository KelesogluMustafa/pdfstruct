#!/usr/bin/env node
// PDFStruct connector for Claude Desktop.
// This bundle contains no engine: it starts the locally installed `pdfstruct-mcp`
// command and passes stdin/stdout through unchanged. Nothing else is executed.
"use strict";
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const DEFAULT = "pdfstruct-mcp";
const configured = (process.env.PDFSTRUCT_MCP_COMMAND || "").trim();
const wanted = configured && !configured.startsWith("${") ? configured : DEFAULT;

// A bare command name is looked up on PATH here, so no shell is ever involved.
function resolve(command) {
  if (command.includes("/") || command.includes("\\")) return command;
  const extensions = process.platform === "win32" ? [".exe", ".cmd", ".bat"] : [""];
  for (const folder of (process.env.PATH || "").split(path.delimiter)) {
    for (const extension of extensions) {
      const candidate = path.join(folder, command + extension);
      if (folder && fs.existsSync(candidate)) return candidate;
    }
  }
  return command;
}

const target = resolve(wanted);
const isBatch = process.platform === "win32" && /\.(cmd|bat)$/i.test(target);
const child = isBatch
  ? spawn(process.env.ComSpec || "cmd.exe", ["/d", "/c", target], {
      stdio: ["pipe", "pipe", "inherit"],
      windowsHide: true,
    })
  : spawn(target, [], { stdio: ["pipe", "pipe", "inherit"], windowsHide: true });

child.on("error", (error) => {
  process.stderr.write(
    `PDFStruct was not found (${wanted}): ${error.message}\n` +
      'Install it first (setup-windows.cmd, or: pip install "pdfstruct[mcp]") and set the ' +
      "path to pdfstruct-mcp in the extension settings.\n",
  );
  process.exit(1);
});
process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);
child.stdin.on("error", () => {});
process.stdin.on("end", () => child.stdin.end());
child.on("exit", (code, signal) => process.exit(signal ? 1 : (code ?? 0)));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill());
