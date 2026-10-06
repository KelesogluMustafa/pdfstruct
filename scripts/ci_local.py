#!/usr/bin/env python3
"""PDFStruct local CI: one command that checks import, tests, build, a clean
wheel install, every console script and a small end-to-end run.

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
                         "pdfstruct/export.py", "pdfstruct/ocr.py"):
            if required not in names:
                missing.append(required)
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


def step_native(venv: Path, work: Path) -> None:
    pdf = make_fixture(work)
    out = sh(script_path(venv, "pdfstruct"), pdf, cwd=work)
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
                            ("OCR", lambda: step_ocr(venv, work))):
            if not installed:
                report(label, "SKIPPED (wheel not installed)")
                continue
            try:
                report(label, step())
            except Exception as exc:
                fail(label, exc)


    print(f"\nRESULT: {'FAIL' if failed else 'PASS'}  ({time.time() - started:.0f}s)")
    for label, text in details:
        print(f"\n--- {label} ---\n{text.rstrip()[-6000:]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
