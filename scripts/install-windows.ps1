<#
.SYNOPSIS
  Installs PDFStruct from a release wheel into its own, versioned folder in your user profile.

.DESCRIPTION
  Creates %USERPROFILE%\.local\pdfstruct\v<version> (a private Python environment), installs
  the wheel there with the MCP server and the desktop window, checks the result (import,
  command line, MCP server) and only then points
      %USERPROFILE%\.local\pdfstruct\current
  at it. Claude (plugin and .mcpb) starts current\Scripts\pdfstruct-mcp.exe.

  Nothing is linked to a source checkout, the system Python packages are not touched, other
  installed versions are kept, and running the script again only repairs that one folder.
  If a check fails, the previously active version stays active.

  Run it through install-windows.cmd, or:
      powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Wheel <path>

.PARAMETER Wheel
  Path to pdfstruct-<version>-py3-none-any.whl. Default: the single wheel next to this script,
  in its parent folder, or in a dist folder there.

.PARAMETER Root
  Parent folder of the versioned installs. Default: %USERPROFILE%\.local\pdfstruct

.PARAMETER Extras
  Optional parts to install. Default: mcp,gui

.PARAMETER NoActivate
  Install and check, but leave "current" pointing where it is.

.PARAMETER Repair
  Reinstall the files of a version that is already installed. Close Claude first: a running
  MCP server keeps its files in use.

.PARAMETER DryRun
  Print what would be done and stop.
#>
param(
    [string]$Wheel = "",
    [string]$Root = "",
    [string]$Extras = "mcp,gui",
    [switch]$NoActivate,
    [switch]$Repair,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "runtime-common.ps1")

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
    $parent = Split-Path -Parent $PSScriptRoot
    $places = @($PSScriptRoot, $parent, (Join-Path $parent "dist"))
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

$Root = Get-PdfstructRoot $Root
$Target = Join-Path $Root "v$Version"
$VenvPython = Join-Path $Target "Scripts\python.exe"
$Stable = Join-Path $Root "current\Scripts"
$activeBefore = Get-ActiveVersion $Root

Write-Host "PDFStruct $Version"
Write-Host "  wheel:  $Wheel"
Write-Host "  target: $Target"
Write-Host "  extras: $Extras"
if ($activeBefore) { Write-Host "  active now: $activeBefore" } else { Write-Host "  active now: none" }

# ---------- checksum, when the release file is next to the wheel ----------
$sums = Join-Path (Split-Path -Parent $Wheel) "SHA256SUMS.txt"
if (Test-Path -LiteralPath $sums) {
    $expected = $null
    foreach ($line in Get-Content -LiteralPath $sums) {
        if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+)$' -and $Matches[2].Trim() -eq $wheelName) { $expected = $Matches[1].ToLower() }
    }
    if ($expected) {
        $actual = (Get-FileHash -LiteralPath $Wheel -Algorithm SHA256).Hash.ToLower()
        if ($actual -ne $expected) { Fail "checksum mismatch for $wheelName (SHA256SUMS.txt). Nothing was installed." }
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
Write-Host ""
$present = $null
if (Test-Path -LiteralPath $VenvPython) {
    try { $present = & $VenvPython -c "from importlib import metadata; print(metadata.version('pdfstruct'))" 2>$null } catch { $present = $null }
    if ($LASTEXITCODE -ne 0) { $present = $null }
}
if ($present -eq $Version -and -not $Repair) {
    # Files of a running MCP server are in use; an installed version is checked, not rewritten.
    Write-Host "PDFStruct $Version is already installed here; its files are not rewritten (use -Repair to force)."
} else {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Host "Creating the environment with Python $pythonVersion ..."
        New-Item -ItemType Directory -Force -Path $Root | Out-Null
        Invoke-Checked $python.Exe ($python.Pre + @("-m", "venv", $Target))
    } else {
        Write-Host "Environment exists; repairing it. If this fails with 'file in use', close Claude and run it again."
    }
    Write-Host "Installing (the first run downloads the OCR packages; this can take several minutes) ..."
    $spec = $Wheel
    if ($Extras) { $spec = $Wheel + "[" + $Extras + "]" }
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--disable-pip-version-check", "--quiet", $spec)
    # make sure the package files really come from this wheel
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--disable-pip-version-check", "--quiet", "--force-reinstall", "--no-deps", $Wheel)
}

# ---------- check the new runtime before anything points at it ----------
Write-Host ""
Write-Host "Checking the new runtime ..."
& $VenvPython (Join-Path $PSScriptRoot "verify_runtime.py") --expect $Version
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: the new runtime did not pass its checks. It was NOT activated." -ForegroundColor Red
    if ($activeBefore) { Write-Host "The active version is still $activeBefore." }
    Write-Host "The failed install is left at $Target for inspection; running this again repairs it."
    exit 1
}

# ---------- activate ----------
if ($NoActivate) {
    Write-Host ""
    Write-Host "Installed and checked PDFStruct $Version. Not activated (-NoActivate)." -ForegroundColor Green
    exit 0
}
try {
    $previous = Set-ActiveVersion $Root $Version
} catch {
    Fail "the runtime is installed and checked, but could not be activated: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "PDFStruct $Version is installed and active (not linked to any source folder)." -ForegroundColor Green
if ($previous -and $previous -ne $Version) { Write-Host "  previous version kept for rollback: $previous  (update-windows.cmd -Rollback)" }
Write-Host "  command line: $(Join-Path $Stable 'pdfstruct.exe')"
if ($Extras -match "gui") { Write-Host "  window:       $(Join-Path $Stable 'pdfstruct-gui.exe')" }
if ($Extras -match "mcp") {
    Write-Host "  MCP server:   $(Join-Path $Stable 'pdfstruct-mcp.exe')"
    Write-Host ""
    Write-Host "Claude Code / Cowork:  install the plugin  pdfstruct-plugin.zip"
    Write-Host "Claude Desktop chat:   install the extension  pdfstruct-$Version.mcpb  (Settings -> Extensions)"
    Write-Host "Both start the 'current' runtime, so they follow later updates without reinstalling."
}
exit 0
