<#
.SYNOPSIS
  Installs PDFStruct from a release wheel into its own, versioned folder in your user profile.

.DESCRIPTION
  Creates %USERPROFILE%\.local\pdfstruct\v<version> (a private Python environment) and installs
  the wheel there with the MCP server and the desktop window. Nothing is linked to a source
  checkout, the system Python packages are not touched, and running the script again only
  repairs or updates that one folder. Claude (Code and Desktop) is pointed at
      %USERPROFILE%\.local\pdfstruct\v<version>\Scripts\pdfstruct-mcp.exe

  Run it through install-windows.cmd, or:
      powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Wheel <path>

.PARAMETER Wheel
  Path to pdfstruct-<version>-py3-none-any.whl. Default: the single wheel next to this script,
  in .\dist or in ..\dist.

.PARAMETER Root
  Parent folder of the versioned installs. Default: %USERPROFILE%\.local\pdfstruct

.PARAMETER Extras
  Optional parts to install. Default: mcp,gui

.PARAMETER DryRun
  Print what would be done and stop.
#>
param(
    [string]$Wheel = "",
    [string]$Root = "",
    [string]$Extras = "mcp,gui",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { Fail "command failed ($LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}

# ---------- the wheel ----------
if (-not $Wheel) {
    $places = @($PSScriptRoot, (Join-Path $PSScriptRoot "dist"), (Join-Path $PSScriptRoot "..\dist"))
    $found = @()
    foreach ($place in $places) {
        if (Test-Path -LiteralPath $place) {
            $found += @(Get-ChildItem -LiteralPath $place -Filter "pdfstruct-*-py3-none-any.whl" -File)
        }
    }
    if ($found.Count -eq 0) { Fail "no pdfstruct wheel found. Download it from the GitHub release and pass it with -Wheel." }
    if ($found.Count -gt 1) { Fail "several wheels found; choose one with -Wheel: $($found.Name -join ', ')" }
    $Wheel = $found[0].FullName
}
if (-not (Test-Path -LiteralPath $Wheel -PathType Leaf)) { Fail "wheel not found: $Wheel" }
$Wheel = (Resolve-Path -LiteralPath $Wheel).Path
$wheelName = Split-Path -Leaf $Wheel
if ($wheelName -notmatch '^pdfstruct-(\d+\.\d+\.\d+)-py3-none-any\.whl$') { Fail "not a PDFStruct release wheel: $wheelName" }
$Version = $Matches[1]

if (-not $Root) { $Root = Join-Path $HOME ".local\pdfstruct" }
$Target = Join-Path $Root "v$Version"
$VenvPython = Join-Path $Target "Scripts\python.exe"
$Mcp = Join-Path $Target "Scripts\pdfstruct-mcp.exe"
$Cli = Join-Path $Target "Scripts\pdfstruct.exe"
$Gui = Join-Path $Target "Scripts\pdfstruct-gui.exe"

Write-Host "PDFStruct $Version"
Write-Host "  wheel:  $Wheel"
Write-Host "  target: $Target"
Write-Host "  extras: $Extras"

# ---------- checksum, when the release file is next to the wheel ----------
$sums = Join-Path (Split-Path -Parent $Wheel) "SHA256SUMS.txt"
if (Test-Path -LiteralPath $sums) {
    $expected = $null
    foreach ($line in Get-Content -LiteralPath $sums) {
        if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+)$' -and $Matches[2].Trim() -eq $wheelName) { $expected = $Matches[1].ToLower() }
    }
    if ($expected) {
        $actual = (Get-FileHash -LiteralPath $Wheel -Algorithm SHA256).Hash.ToLower()
        if ($actual -ne $expected) { Fail "checksum mismatch for $wheelName (SHA256SUMS.txt)" }
        Write-Host "  checksum: OK"
    } else {
        Write-Host "  checksum: skipped ($wheelName is not listed in SHA256SUMS.txt)"
    }
} else {
    Write-Host "  checksum: skipped (no SHA256SUMS.txt next to the wheel)"
}

# ---------- a Python 3.10 - 3.13 to build the environment with ----------
$python = $null
$candidates = @(
    @{ Exe = "py"; Pre = @("-3.13") }, @{ Exe = "py"; Pre = @("-3.12") }, @{ Exe = "py"; Pre = @("-3.11") },
    @{ Exe = "py"; Pre = @("-3.10") }, @{ Exe = "python"; Pre = @() }
)
foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
    $probe = $null
    try { $probe = & $candidate.Exe @($candidate.Pre + @("-c", "import sys; print('%d.%d' % sys.version_info[:2])")) 2>$null } catch { $probe = $null }
    if ($LASTEXITCODE -eq 0 -and $probe -match '^3\.(10|11|12|13)$') { $python = $candidate; $pythonVersion = $probe; break }
}
if (-not $python -and -not (Test-Path -LiteralPath $VenvPython)) {
    Fail "Python 3.10 - 3.13 was not found. Install it from https://www.python.org/downloads/ and run this again."
}

if ($DryRun) {
    Write-Host ""
    Write-Host "DRY RUN: nothing was changed."
    exit 0
}

# ---------- the environment ----------
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host ""
    Write-Host "Creating the environment with Python $pythonVersion ..."
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    Invoke-Checked $python.Exe ($python.Pre + @("-m", "venv", $Target))
} else {
    Write-Host ""
    Write-Host "Environment exists; updating it."
}

Write-Host "Installing (the first run downloads the OCR packages; this can take several minutes) ..."
$spec = $Wheel
if ($Extras) { $spec = $Wheel + "[" + $Extras + "]" }
Invoke-Checked $VenvPython @("-m", "pip", "install", "--disable-pip-version-check", "--quiet", $spec)
# same version again: make sure the files really come from this wheel
Invoke-Checked $VenvPython @("-m", "pip", "install", "--disable-pip-version-check", "--quiet", "--force-reinstall", "--no-deps", $Wheel)

# ---------- verify: a normal, non-editable install of exactly this version ----------
$check = @"
import json, sys
from importlib import metadata
import pdfstruct
dist = metadata.distribution('pdfstruct')
direct = dist.read_text('direct_url.json')
editable = bool(direct and json.loads(direct).get('dir_info', {}).get('editable'))
inside = pdfstruct.__file__.lower().startswith(sys.prefix.lower())
print('%s|%s|%s' % (pdfstruct.__version__, int(editable), int(inside)))
"@
$result = (& $VenvPython -c $check)
if ($LASTEXITCODE -ne 0) { Fail "the installed package cannot be imported" }
$parts = "$result".Trim().Split("|")
if ($parts[0] -ne $Version) { Fail "installed version is $($parts[0]), expected $Version" }
if ($parts[1] -ne "0") { Fail "the install is editable (linked to a source folder); that is not allowed here" }
if ($parts[2] -ne "1") { Fail "pdfstruct was imported from outside $Target" }
if (-not (Test-Path -LiteralPath $Cli)) { Fail "missing $Cli" }
if ($Extras -match "mcp" -and -not (Test-Path -LiteralPath $Mcp)) { Fail "missing $Mcp" }

Write-Host ""
Write-Host "Installed PDFStruct $Version (not linked to any source folder)." -ForegroundColor Green
Write-Host "  command line: $Cli"
if ($Extras -match "gui") { Write-Host "  window:       $Gui" }
if ($Extras -match "mcp") {
    Write-Host "  MCP server:   $Mcp"
    Write-Host ""
    Write-Host "Claude Code:"
    Write-Host "  claude mcp add --scope user pdfstruct -- `"$Mcp`""
    Write-Host "Claude for Windows: install pdfstruct-$Version.mcpb (Settings -> Extensions)."
}
exit 0
