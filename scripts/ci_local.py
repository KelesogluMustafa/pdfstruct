#!/usr/bin/env python3
"""PDFStruct local CI: one command that checks import, tests, build, a clean
wheel install, every console script, end-to-end runs for the input types, documents
created from text, the optional extras (desktop window without a display, MCP server
over stdio) and the skill archive.

    python scripts/ci_local.py          (from the repository root, inside the dev venv)

Prints one line per step; a step's full output is shown only when it fails.
OCR is reported as PASS / SKIPPED / FAIL and never breaks the run when no OCR
environment is available. Exit code 0 only when every required step passed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
ALIASES = ["pdfjson", "pdfhtml", "pdftxt", "pdfmd", "pdfcsv", "pdfxlsx", "pdfdocx",
           "pdfjsonl", "pdfsqlite"]
SCRIPTS = ["pdfstruct", *ALIASES]
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PIP_DISABLE_PIP_VERSION_CHECK="1")


class StepFailed(Exception):
    pass


def sh(*cmd, cwd: Path | None = None, timeout: int = 900) -> str:
    """Run a command; return its combined output, raise StepFailed on a non-zero exit."""
    result = subprocess.run([str(c) for c in cmd], cwd=cwd, env=ENV, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise StepFailed(f"$ {' '.join(str(c) for c in cmd)}\nexit {result.returncode}\n{output}")
    return output


def venv_bin(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin")


def venv_python(venv: Path) -> Path:
    return venv_bin(venv) / ("python.exe" if os.name == "nt" else "python")


def script_path(venv: Path, name: str) -> Path:
    return venv_bin(venv) / (name + (".exe" if os.name == "nt" else ""))


# ---------------------------------------------------------------- steps

def step_import() -> str:
    out = sh(sys.executable, "-c",
             "import pdfstruct, json; from importlib import metadata;"
             "print(json.dumps([pdfstruct.__version__, metadata.version('pdfstruct')]))")
    package_version, installed_version = json.loads(out.strip().splitlines()[-1])
    if package_version != installed_version:
        raise StepFailed(f"__version__ {package_version} != installed {installed_version}"
                         " (run: pip install -e .)")
    return package_version


def step_tests() -> str:
    out = sh(sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", cwd=ROOT)
    summary = out.strip().splitlines()[-1]  # e.g. "47 passed, 1 skipped in 30.1s"
    passed = int(summary.split(" passed")[0].split()[-1]) if " passed" in summary else 0
    total = passed + sum(int(part.split()[0]) for part in summary.split(",")
                         if any(k in part for k in ("failed", "error")))
    if "failed" in summary or "error" in summary:
        raise StepFailed(out)
    return f"{passed}/{total} PASS" + (" (+skipped)" if "skipped" in summary else "")


def step_build(version: str) -> tuple[Path, Path]:
    shutil.rmtree(DIST, ignore_errors=True)
    sh(sys.executable, "-m", "build", "--outdir", DIST, cwd=ROOT)
    wheels, sdists = sorted(DIST.glob("*.whl")), sorted(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise StepFailed(f"expected one wheel and one sdist in {DIST}: {os.listdir(DIST)}")
    if version not in wheels[0].name or version not in sdists[0].name:
        raise StepFailed(f"built artifacts do not carry version {version}: {wheels[0].name}")

    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        entry_points = next((n for n in names if n.endswith("entry_points.txt")), None)
        if entry_points is None:
            raise StepFailed("wheel has no entry_points.txt")
        declared = wheel.read(entry_points).decode()
        missing = [s for s in SCRIPTS if f"{s} = pdfstruct.cli:" not in declared]
        for required in ("pdfstruct/__init__.py", "pdfstruct/cli.py", "pdfstruct/extract.py",
                         "pdfstruct/export.py", "pdfstruct/ocr.py", "pdfstruct/service.py",
                         "pdfstruct/pdfwriter.py", "pdfstruct/mcp_server.py",
                         "pdfstruct/create.py", "pdfstruct/docwriter.py",
                         "pdfstruct/inputs/__init__.py", "pdfstruct/inputs/image.py",
                         "pdfstruct/gui/app.py", "pdfstruct/gui/window.py",
                         "pdfstruct/gui/create_panel.py"):
            if required not in names:
                missing.append(required)
        for extra in ("pdfstruct-mcp = pdfstruct.mcp_server:main",
                      "pdfstruct-create = pdfstruct.cli:create",
                      "pdfstruct-gui = pdfstruct.gui.app:main"):
            if extra not in declared:
                missing.append(extra)
        heavy = [n for n in names if n.lower().endswith(
            (".ttf", ".otf", ".pdmodel", ".pdiparams", ".onnx", ".pdf", ".raw.json", ".dll", ".exe"))]
        if heavy:
            raise StepFailed("the wheel must not carry fonts, models, documents or binaries: "
                             + ", ".join(heavy[:5]))
    with tarfile.open(sdists[0]) as sdist:
        names = sdist.getnames()
        for required in ("pyproject.toml", "src/pdfstruct/__init__.py", "README.md", "LICENSE"):
            if not any(n.endswith("/" + required) for n in names):
                missing.append("sdist:" + required)
    if missing:
        raise StepFailed("missing from built artifacts: " + ", ".join(missing))
    return wheels[0], sdists[0]


def step_wheel_install(wheel: Path, venv: Path) -> None:
    sh(sys.executable, "-m", "venv", venv)
    sh(venv_python(venv), "-m", "pip", "install", "-q", wheel)
    sh(venv_python(venv), "-c", "import pdfstruct")


def step_cli(venv: Path, version: str) -> str:
    failures = []
    for name in SCRIPTS:
        script = script_path(venv, name)
        try:
            if not script.is_file():
                raise StepFailed(f"{script} not installed")
            help_text = sh(script, "--help", cwd=venv)
            if f"{name} belge.pdf" not in help_text:
                raise StepFailed(f"{name} --help has no usage line:\n{help_text}")
            printed = sh(script, "--version", cwd=venv).strip()
            if printed != f"pdfstruct {version}":
                raise StepFailed(f"{name} --version printed {printed!r}")
        except StepFailed as exc:
            failures.append(str(exc))
    if failures:
        raise StepFailed("\n".join(failures))
    return f"{len(SCRIPTS)}/{len(SCRIPTS)} PASS"


def make_fixture(folder: Path) -> Path:
    """Two-page native PDF with umlauts, built with the dev venv (reportlab)."""
    sys.path.insert(0, str(ROOT / "tests"))
    from conftest import make_text_pdf  # noqa: E402
    return make_text_pdf(folder / "belge (ä).pdf", pages=2)


def step_extras(wheel: Path, venv: Path, work: Path) -> str:
    """Install the wheel with [gui,mcp] into the clean venv; open the window without a
    display and talk to the MCP server over stdio."""
    sh(venv_python(venv), "-m", "pip", "install", "-q", f"{wheel}[gui,mcp]", timeout=1800)
    for name in ("pdfstruct-gui", "pdfstruct-mcp"):
        if not script_path(venv, name).is_file():
            raise StepFailed(f"{name} entry point not installed")

    gui_env = dict(ENV, QT_QPA_PLATFORM="offscreen")
    done = subprocess.run([str(venv_python(venv)), "-m", "pdfstruct.gui.app", "--smoke-test"],
                          cwd=work, env=gui_env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)
    line = next((l for l in done.stdout.splitlines() if l.startswith("GUI_SMOKE ")), None)
    if done.returncode != 0 or line is None:
        raise StepFailed(f"gui smoke: exit {done.returncode}\n{done.stdout}\n{done.stderr}")
    gui = json.loads(line[len("GUI_SMOKE "):])
    if not (gui["visible"] and gui["closed"]) or gui["ocr_loaded"] or len(gui["formats"]) != 10:
        raise StepFailed(f"gui smoke reported: {gui}")
    if gui.get("tabs") != ["Convert files", "Create from text"] or len(gui["create_formats"]) != 5:
        raise StepFailed(f"gui smoke: the Create from text tab is missing: {gui}")

    note = work / "mcp notiz.txt"
    note.write_text("MCP-GEHEIM Inhalt " * 300, encoding="utf-8")
    client = work / "mcp_client.py"
    client.write_text(MCP_CLIENT, encoding="utf-8")
    out = sh(venv_python(venv), client, note, cwd=work, timeout=600)
    answer = json.loads(out.strip().splitlines()[-1])
    if answer["tools"] != ["convert", "create_document", "inspect", "read_excerpt", "search",
                           "supported_formats"]:
        raise StepFailed(f"mcp tools: {answer['tools']}")
    if not answer["converted_ok"] or answer["leaked_text"] or answer["excerpt_chars"] != 2000:
        raise StepFailed(f"mcp answer: {answer}")
    if not (work / "output" / "mcp notiz.txt.pdf").is_file():
        raise StepFailed("mcp convert did not write the pdf output")
    expected = [str(work / "mcp created" / f"MCP_VORLAGE.{ext}") for ext in ("docx", "pdf")]
    if answer["created"] != {"status": "created", "outputs": expected, "warnings": []}:
        raise StepFailed(f"mcp create_document: {answer['created']}")
    if not all(Path(path).is_file() for path in expected):
        raise StepFailed("mcp create_document did not write its files")
    return f"PASS (gui {gui['platform']}, mcp stdio)"


MCP_CLIENT = '''
import asyncio, json, os, sys
import mcp
from mcp.client.stdio import StdioServerParameters

async def main(path):
    params = StdioServerParameters(command=sys.executable, args=["-m", "pdfstruct.mcp_server"])
    async with mcp.Client(params) as client:
        tools = sorted(t.name for t in (await client.list_tools()).tools)
        converted = (await client.call_tool("convert", {"paths": [path], "formats": ["pdf", "json"]})).content[0].text
        excerpt = json.loads((await client.call_tool(
            "read_excerpt", {"path_or_output": path, "max_chars": 500000})).content[0].text)
        created = (await client.call_tool("create_document", {
            "name": "MCP_VORLAGE", "content": "# MCP-GEHEIM {{PLACEHOLDER}}\\n\\n- eins\\n- zwei\\n",
            "formats": ["docx", "pdf"], "output_dir": os.path.join(os.path.dirname(path), "mcp created")})).content[0].text
    print(json.dumps({"tools": tools, "converted_ok": json.loads(converted)["ok"],
                      "leaked_text": "MCP-GEHEIM" in converted + created,
                      "excerpt_chars": excerpt["chars_returned"], "created": json.loads(created)}))

asyncio.run(main(sys.argv[1]))
'''


def step_skill() -> str:
    """The skill ZIP and the plugin ZIP, both built from plugin/skills/pdfstruct."""
    import zipfile
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_release_assets as assets
    with tempfile.TemporaryDirectory(prefix="pdfstruct_skill_") as tmp:
        skill = assets.build_skill(Path(tmp))
        plugin = assets.build_plugin(Path(tmp), assets.version())
        with zipfile.ZipFile(skill) as archive:
            if archive.namelist() != ["pdfstruct/SKILL.md"]:
                raise StepFailed(f"skill zip entries: {archive.namelist()}")
            text = archive.read("pdfstruct/SKILL.md")
        with zipfile.ZipFile(plugin) as archive:
            if archive.read("skills/pdfstruct/SKILL.md") != text:
                raise StepFailed("the plugin and the skill zip carry different SKILL.md content")
    return "PASS (skill zip and plugin zip from one source)"


def step_native(venv: Path, work: Path) -> None:
    pdf = make_fixture(work)
    # bare `pdfstruct` is interactive; without a terminal it must exit 2 at once, never hang
    probe = subprocess.run([str(script_path(venv, "pdfstruct"))], cwd=work, env=ENV, input="",
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=120)
    if probe.returncode != 2 or "--format" not in probe.stdout:
        raise StepFailed(f"bare pdfstruct without a TTY: exit {probe.returncode}\n{probe.stdout}")
    out = sh(script_path(venv, "pdfstruct"), pdf, "--format", "json", cwd=work)
    if "FAILED: 0" not in out or "PROCESSED: 1" not in out:
        raise StepFailed(out)
    raw = work / "output" / "belge (ä).raw.json"
    if not raw.is_file():
        raise StepFailed(f"missing {raw}")
    out = sh(script_path(venv, "pdftxt"), cwd=work)  # no argument: PDFs in the folder
    if "RAW_REUSED: 1" not in out:
        raise StepFailed(out)
    text = (work / "output" / "belge (ä).txt").read_text(encoding="utf-8")
    if "ä ö ü Ä Ö Ü ß" not in text or "===== Page 2 / 2 =====" not in text:
        raise StepFailed("txt export lost umlauts or pages:\n" + text[:500])
    out = sh(script_path(venv, "pdfstruct"), "--format", "md", pdf, cwd=work)
    if "EXPORTED: 1" not in out or not (work / "output" / "belge (ä).md").is_file():
        raise StepFailed(out)
    # other inputs and the PDF output, through the installed commands
    note = work / "not (ğ).txt"
    note.write_text("Çağrı Öğretmen İstanbul\n\nStraße größer", encoding="utf-8")
    page = work / "seite.html"
    page.write_text("<h1>Titel</h1><p>Absatz</p><script>x()</script>", encoding="utf-8")
    out = sh(script_path(venv, "pdfstruct"), note, "--format", "pdf,docx,json", cwd=work)
    produced = work / "output" / "not (ğ).txt.pdf"
    if out.count("\u2713") != 3 or not produced.read_bytes().startswith(b"%PDF-"):
        raise StepFailed(out)
    out = sh(script_path(venv, "pdfxlsx"), page, cwd=work)
    if "EXPORTED: 1" not in out or not (work / "output" / "seite.html.xlsx").is_file():
        raise StepFailed(out)
    out = sh(script_path(venv, "pdfstruct"), pdf, "--format", "pdf", cwd=work)
    if "SKIPPED: 1 (already PDF" not in out or (work / "output" / "belge (ä).pdf").exists():
        raise StepFailed(out)


def step_create(venv: Path, work: Path, version: str) -> str:
    """pdfstruct-create from the clean venv: a content file, standard input, no overwrite."""
    script = script_path(venv, "pdfstruct-create")
    if sh(script, "--version", cwd=work).strip() != f"pdfstruct {version}":
        raise StepFailed("pdfstruct-create --version")
    text = "# Şablon {{PROJECT_NAME}}\n\nStraße größer – Çağrı\n\n1. eins\n2. zwei\n\n| A | B |\n|---|---|\n| 1 | {{X}} |\n"
    source = work / "vorlage (ş).md"
    source.write_text(text, encoding="utf-8")
    out = sh(script, "--content-file", source, "--name", "CI_TEMPLATE", "--format", "docx,pdf,html,md,txt",
             "--output", work / "created", cwd=work)
    names = sorted(p.name for p in (work / "created").iterdir())
    if names != sorted(f"CI_TEMPLATE.{ext}" for ext in ("docx", "pdf", "html", "md", "txt")):
        raise StepFailed(f"created files: {names}\n{out}")
    if out.count("CREATED: ") != 5 or "PROJECT_NAME" in out or "Straße" in out:
        raise StepFailed("pdfstruct-create must print five paths and no text:\n" + out)
    if (work / "created" / "CI_TEMPLATE.md").read_text(encoding="utf-8") != text:
        raise StepFailed("the Markdown output is not the text that went in")
    if "{{PROJECT_NAME}}" not in (work / "created" / "CI_TEMPLATE.txt").read_text(encoding="utf-8"):
        raise StepFailed("a placeholder was lost")
    piped = subprocess.run([str(script), "--name", "CI_TEMPLATE", "--format", "txt", "--output",
                            str(work / "created")], input=text.encode("utf-8"), cwd=work, env=ENV,
                           capture_output=True, timeout=300)
    if piped.returncode != 1 or b"CONFLICT:" not in piped.stdout:
        raise StepFailed(f"an existing file must be kept: exit {piped.returncode}\n{piped.stdout!r}")
    piped = subprocess.run([str(script), "--name", "CI_PIPED", "--output", str(work / "created")],
                           input=text.encode("utf-8"), cwd=work, env=ENV, capture_output=True, timeout=300)
    if piped.returncode != 0 or not (work / "created" / "CI_PIPED.docx").is_file():
        raise StepFailed(f"standard input: exit {piped.returncode}\n{piped.stdout!r}{piped.stderr!r}")
    return "PASS (content file, stdin, 5 formats)"


def step_ocr(venv: Path, work: Path) -> str:
    """OCR with the wheel installed in the clean venv (never an external OCR Python).

    PASS    a generated scan PDF came back with method "ocr"
    SKIPPED this platform has no paddlepaddle wheel (reported, not hidden)
    FAIL    anything else, including OCR packages missing on a supported platform
    """
    from pdfstruct import ocr
    probe = sh(venv_python(venv), "-c",
               "from pdfstruct import ocr; print(int(ocr.available()), int(ocr.platform_supported()))")
    installed, supported = (int(v) for v in probe.split()[-2:])
    if not installed:
        if not supported:
            return "SKIPPED (unsupported platform: no paddlepaddle wheel)"
        raise StepFailed("OCR packages missing in the clean venv although the platform is "
                         "supported; check the dependency markers in pyproject.toml")
    sys.path.insert(0, str(ROOT / "tests"))
    from conftest import make_scan_pdf  # noqa: E402
    pdf = make_scan_pdf(work / "scan.pdf")
    out = sh(script_path(venv, "pdfjson"), pdf, cwd=work, timeout=1800)
    if "FAILED: 0" not in out or "OCR FILES: 1" not in out:
        raise StepFailed(out)
    raw = json.loads((work / "output" / "scan.raw.json").read_text(encoding="utf-8"))
    engine = raw.get("ocr_engine") or {}
    if raw.get("extraction_method") != "ocr" or not engine.get("engine", "").startswith("paddleocr"):
        raise StepFailed(f"unexpected raw.json header: {dict((k, raw.get(k)) for k in ('extraction_method', 'ocr_engine', 'warnings'))}")
    if "python" in engine:
        raise StepFailed(f"OCR ran through an external interpreter: {engine}")
    text = raw["pages"][0]["text"]
    if "Hallo" not in text:
        raise StepFailed("OCR text does not contain the fixture words: " + text[:200])
    return f"PASS ({engine.get('device')}, {Path(engine.get('model_cache_dir', '')).name})"


# ---------------------------------------------------------------- runner

def main() -> int:
    print("PDFStruct Local CI\n")
    started = time.time()
    failed = False
    details = []

    def report(label: str, value: str) -> None:
        print(f"{label}: {value}")

    def fail(label: str, exc: Exception) -> None:
        nonlocal failed
        failed = True
        report(label, "FAIL")
        details.append((label, str(exc)))

    version = None
    try:
        version = step_import()
        report("IMPORT", "PASS")
    except Exception as exc:
        fail("IMPORT", exc)

    try:
        report("TESTS", step_tests())
    except Exception as exc:
        fail("TESTS", exc)

    wheel = None
    if version:
        try:
            wheel, _ = step_build(version)
            report("BUILD", "PASS")
        except Exception as exc:
            fail("BUILD", exc)
    else:
        report("BUILD", "SKIPPED (import failed)")

    with tempfile.TemporaryDirectory(prefix="pdfstruct_ci_") as tmp:
        venv, work = Path(tmp) / "venv", Path(tmp) / "work"
        work.mkdir()
        installed = False
        if wheel:
            try:
                step_wheel_install(wheel, venv)
                installed = True
                report("WHEEL INSTALL", "PASS")
            except Exception as exc:
                fail("WHEEL INSTALL", exc)
        else:
            report("WHEEL INSTALL", "SKIPPED (no wheel)")
        for label, step in (("CLI", lambda: step_cli(venv, version)),
                            ("NATIVE", lambda: step_native(venv, work) or "PASS"),
                            ("CREATE", lambda: step_create(venv, work, version)),
                            ("OCR", lambda: step_ocr(venv, work)),
                            ("EXTRAS", lambda: step_extras(wheel, venv, work))):
            if not installed:
                report(label, "SKIPPED (wheel not installed)")
                continue
            try:
                report(label, step())
            except Exception as exc:
                fail(label, exc)


    try:
        report("SKILL", step_skill())
    except Exception as exc:
        fail("SKILL", exc)

    print(f"\nRESULT: {'FAIL' if failed else 'PASS'}  ({time.time() - started:.0f}s)")
    for label, text in details:
        print(f"\n--- {label} ---\n{text.rstrip()[-6000:]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
