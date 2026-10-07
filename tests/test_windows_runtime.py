"""Windows runtime layout: versioned installs, the 'current' pointer, update and rollback.

The update flow is exercised with a local release folder and small stand-in runtimes, so no
test downloads anything, installs the real package or touches %USERPROFILE%\\.local\\pdfstruct.
"""
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import pdfstruct
from conftest import TOOL_DIR

pytestmark = pytest.mark.skipif(os.name != "nt", reason="the installer and updater are for Windows")

SCRIPTS = TOOL_DIR / "scripts"
VERSION = pdfstruct.__version__


def powershell(script: Path, *args, stdin: str | None = None, env: dict | None = None):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(script), *map(str, args)], capture_output=True, text=True,
                          input=stdin, timeout=600, env={**os.environ, **(env or {})})


def call(root: Path, expression: str) -> str:
    """Run one expression with runtime-common.ps1 loaded; returns its trimmed output."""
    command = f". '{SCRIPTS / 'runtime-common.ps1'}'; $r = '{root}'; {expression}"
    done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                          capture_output=True, text=True, timeout=120)
    return (done.stdout + done.stderr).strip()


def fake_runtime(root: Path, version: str) -> Path:
    """A real (pip-less) Python environment whose 'pdfstruct' only knows its version."""
    target = root / f"v{version}"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(target)], check=True)
    package = target / "Lib" / "site-packages" / "pdfstruct"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    return target


def active(root: Path) -> str:
    return call(root, "Get-ActiveVersion $r")


def release_folder(folder: Path, version: str, checksum_ok: bool = True) -> Path:
    folder.mkdir(parents=True)
    wheel = folder / f"pdfstruct-{version}-py3-none-any.whl"
    wheel.write_bytes(f"stand-in wheel {version}".encode())
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest() if checksum_ok else "0" * 64
    (folder / "SHA256SUMS.txt").write_text(f"{digest} *{wheel.name}\n", encoding="utf-8")
    (folder / "release.json").write_text(json.dumps({"tag_name": f"v{version}"}), encoding="utf-8")
    return folder


@pytest.fixture
def stub_installer(tmp_path) -> Path:
    """Stands in for install-windows.ps1: STUB_MODE = ok | fail | unchecked."""
    stub = tmp_path / "stub-installer.ps1"
    stub.write_text(f"""param([string]$Wheel, [string]$Root)
. '{SCRIPTS / 'runtime-common.ps1'}'
if ($env:STUB_MODE -eq 'fail') {{ Write-Host 'stub: install failed'; exit 1 }}
(Split-Path -Leaf $Wheel) -match '^pdfstruct-(\\d+\\.\\d+\\.\\d+)-' | Out-Null
$version = $Matches[1]
& '{sys.executable}' -m venv --without-pip (Join-Path $Root "v$version")
$package = Join-Path $Root "v$version\\Lib\\site-packages\\pdfstruct"
New-Item -ItemType Directory -Force -Path $package | Out-Null
Set-Content -LiteralPath (Join-Path $package '__init__.py') -Value "__version__ = '$version'" -Encoding ASCII
if ($env:STUB_MODE -eq 'unchecked') {{ Write-Host 'stub: runtime did not pass its checks'; exit 1 }}
Set-ActiveVersion $Root $version | Out-Null
exit 0
""", encoding="utf-8")
    return stub


# ---------------------------------------------------------------- pointer

def test_current_is_a_junction_that_switches_and_remembers_the_previous_version(tmp_path):
    root = tmp_path / "user home" / "pdf struct"  # spaces, as in a real user name
    root.mkdir(parents=True)
    old, new = fake_runtime(root, "0.8.0"), fake_runtime(root, "0.9.0")
    assert active(root) == ""
    call(root, "Set-ActiveVersion $r '0.8.0' | Out-Null")
    assert active(root) == "0.8.0" and not (root / "previous-version.txt").exists()
    current = root / "current"
    assert (current / "Scripts" / "python.exe").is_file() and os.path.realpath(current) == str(old)

    call(root, "Set-ActiveVersion $r '0.9.0' | Out-Null")
    assert active(root) == "0.9.0" and os.path.realpath(current) == str(new)
    assert (root / "previous-version.txt").read_text().strip() == "0.8.0"
    assert (old / "Scripts" / "python.exe").is_file()  # switching deletes nothing
    assert call(root, "(Get-InstalledVersions $r) -join ','") == "0.8.0,0.9.0"
    assert "not installed" in call(root, "try { Set-ActiveVersion $r '7.7.7' } catch { $_.Exception.Message }")
    assert active(root) == "0.9.0"


def test_a_real_folder_named_current_is_never_replaced(tmp_path):
    root = tmp_path / "root"
    fake_runtime(root, "0.9.0")
    (root / "current").mkdir()
    (root / "current" / "keep.txt").write_text("user data", encoding="utf-8")
    message = call(root, "try { Set-ActiveVersion $r '0.9.0' } catch { $_.Exception.Message }")
    assert "not a junction" in message
    assert (root / "current" / "keep.txt").read_text(encoding="utf-8") == "user data"


# ---------------------------------------------------------------- installer

def test_installer_dry_run_targets_the_versioned_folder(tmp_path):
    wheel = tmp_path / f"pdfstruct-{VERSION}-py3-none-any.whl"
    wheel.write_bytes(b"the dry run only reads the name")
    script = SCRIPTS / "install-windows.ps1"
    done = powershell(script, "-Wheel", wheel, "-Root", tmp_path / "root", "-DryRun")
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"PDFStruct {VERSION}" in done.stdout and "DRY RUN" in done.stdout
    assert str(tmp_path / "root" / f"v{VERSION}") in done.stdout and "active now: none" in done.stdout
    assert not (tmp_path / "root").exists()
    default = powershell(script, "-Wheel", wheel, "-DryRun")
    assert str(Path.home() / ".local" / "pdfstruct" / f"v{VERSION}") in default.stdout
    bad = tmp_path / "pdfstruct-dev.whl"
    bad.write_bytes(b"x")
    refused = powershell(script, "-Wheel", bad, "-DryRun")
    assert refused.returncode == 1 and "not a PDFStruct release wheel" in refused.stdout
    (tmp_path / "SHA256SUMS.txt").write_text(f"{'0' * 64} *{wheel.name}\n", encoding="utf-8")
    tampered = powershell(script, "-Wheel", wheel, "-Root", tmp_path / "root", "-DryRun")
    assert tampered.returncode == 1 and "checksum mismatch" in tampered.stdout
    text = script.read_text(encoding="utf-8")
    assert " -e " not in text and "--editable" not in text  # never linked to a source folder
    for name in ("install-windows.cmd", "update-windows.cmd"):
        launcher = (TOOL_DIR / name).read_text(encoding="ascii")
        assert "%~dp0scripts\\" in launcher and "musta" not in launcher


def make_wheel(folder: Path, version: str) -> Path:
    """A valid, tiny wheel named pdfstruct that has no command line and no MCP server."""
    wheel = folder / f"pdfstruct-{version}-py3-none-any.whl"
    info = f"pdfstruct-{version}.dist-info"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("pdfstruct/__init__.py", f'__version__ = "{version}"\n')
        archive.writestr(f"{info}/METADATA", f"Metadata-Version: 2.1\nName: pdfstruct\nVersion: {version}\n")
        archive.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr(f"{info}/RECORD", "")
    return wheel


def test_a_runtime_that_fails_its_checks_is_not_activated(tmp_path):
    root = tmp_path / "root"
    fake_runtime(root, "0.8.0")
    call(root, "Set-ActiveVersion $r '0.8.0' | Out-Null")
    wheel = make_wheel(tmp_path, "0.9.0")
    done = powershell(SCRIPTS / "install-windows.ps1", "-Wheel", wheel, "-Root", root, "-Extras", "")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "CLI: FAIL" in done.stdout and "NOT activated" in done.stdout
    assert "The active version is still 0.8.0" in done.stdout
    assert active(root) == "0.8.0"                                   # the pointer did not move
    assert (root / "v0.9.0" / "Scripts" / "python.exe").is_file()    # left for inspection
    assert not (root / "previous-version.txt").exists()


# ---------------------------------------------------------------- updater

def update(root: Path, release: Path, stub: Path, *args, mode: str = "ok", stdin: str | None = None):
    return powershell(SCRIPTS / "update-windows.ps1", "-Root", root, "-ReleaseDir", release,
                      "-Installer", stub, *args, stdin=stdin, env={"STUB_MODE": mode})


@pytest.fixture
def installed(tmp_path) -> Path:
    root = tmp_path / "root"
    fake_runtime(root, "0.8.0")
    call(root, "Set-ActiveVersion $r '0.8.0' | Out-Null")
    return root


def test_same_version_is_a_no_op(installed, tmp_path, stub_installer):
    done = update(installed, release_folder(tmp_path / "rel", "0.8.0"), stub_installer, "-Yes")
    assert done.returncode == 0 and "up to date" in done.stdout
    assert active(installed) == "0.8.0" and not (installed / "releases").exists()
    older = update(installed, release_folder(tmp_path / "old", "0.7.9"), stub_installer, "-Yes")
    assert "up to date" in older.stdout and active(installed) == "0.8.0"  # never downgrades


def test_check_reports_a_new_version_without_changing_anything(installed, tmp_path, stub_installer):
    done = update(installed, release_folder(tmp_path / "rel", "0.9.0"), stub_installer, "-Check")
    assert done.returncode == 0 and "An update is available: 0.8.0 -> 0.9.0" in done.stdout
    assert "active:       0.8.0" in done.stdout and "latest:       0.9.0" in done.stdout
    assert active(installed) == "0.8.0" and not (installed / "releases").exists()


def test_nothing_happens_without_the_users_yes(installed, tmp_path, stub_installer):
    release = release_folder(tmp_path / "rel", "0.9.0")
    for answer in ("n\n", "\n", ""):
        done = update(installed, release, stub_installer, stdin=answer)
        assert done.returncode == 0 and "Cancelled. Nothing was downloaded or changed." in done.stdout
    assert active(installed) == "0.8.0"
    assert not (installed / "releases").exists() and not (installed / "v0.9.0").exists()


def test_checksum_failure_stops_before_installing(installed, tmp_path, stub_installer):
    done = update(installed, release_folder(tmp_path / "rel", "0.9.0", checksum_ok=False),
                  stub_installer, "-Yes")
    assert done.returncode == 1 and "checksum mismatch" in done.stdout
    assert "the active version is still 0.8.0" in done.stdout
    assert active(installed) == "0.8.0" and not (installed / "v0.9.0").exists()
    assert not list((installed / "releases").rglob("*.whl"))  # the bad download was deleted
    missing = release_folder(tmp_path / "rel2", "0.9.0")
    (missing / "SHA256SUMS.txt").write_text("", encoding="utf-8")
    unlisted = update(installed, missing, stub_installer, "-Yes")
    assert unlisted.returncode == 1 and "does not list" in unlisted.stdout


@pytest.mark.parametrize("mode,new_folder", [("fail", False), ("unchecked", True)])
def test_failed_install_or_failed_checks_leave_the_old_version_active(installed, tmp_path,
                                                                     stub_installer, mode, new_folder):
    done = update(installed, release_folder(tmp_path / "rel", "0.9.0"), stub_installer, "-Yes", mode=mode)
    assert done.returncode == 1 and "could not be installed or did not pass its checks" in done.stdout
    assert "the active version is still 0.8.0" in done.stdout
    assert active(installed) == "0.8.0"
    assert (installed / "v0.8.0" / "Scripts" / "python.exe").is_file()
    assert (installed / "v0.9.0").exists() is new_folder
    assert not (installed / "previous-version.txt").exists()


def test_update_then_rollback_keeps_both_versions(installed, tmp_path, stub_installer):
    done = update(installed, release_folder(tmp_path / "rel", "0.9.0"), stub_installer, stdin="y\n")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Updated: PDFStruct 0.9.0 is active." in done.stdout and "Kept for rollback: 0.8.0" in done.stdout
    assert "do not need to be" in done.stdout and "Restart Claude" in done.stdout
    assert active(installed) == "0.9.0"
    assert (installed / "v0.8.0" / "Scripts" / "python.exe").is_file()  # the old version is kept
    listing = update(installed, tmp_path / "rel", stub_installer, "-List").stdout
    assert "0.8.0  (previous)" in listing and "0.9.0  (active)" in listing

    back = update(installed, tmp_path / "rel", stub_installer, "-Rollback")
    assert back.returncode == 0 and "Rolled back: PDFStruct 0.8.0 is active again (was 0.9.0)" in back.stdout
    assert active(installed) == "0.8.0"
    assert (installed / "v0.9.0" / "Scripts" / "python.exe").is_file()  # rollback deletes nothing
    again = update(installed, tmp_path / "rel", stub_installer, "-Rollback")  # and forward again
    assert again.returncode == 0 and active(installed) == "0.9.0"


def test_rollback_needs_a_working_previous_version(tmp_path, stub_installer):
    root = tmp_path / "root"
    fake_runtime(root, "0.9.0")
    call(root, "Set-ActiveVersion $r '0.9.0' | Out-Null")
    none = update(root, tmp_path, stub_installer, "-Rollback")
    assert none.returncode == 1 and "no recorded previous version" in none.stdout
    (root / "previous-version.txt").write_text("0.8.0\n", encoding="ascii")
    gone = update(root, tmp_path, stub_installer, "-Rollback")
    assert gone.returncode == 1 and "no longer installed" in gone.stdout and active(root) == "0.9.0"
