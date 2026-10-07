<#
.SYNOPSIS
  Checks GitHub for a newer stable PDFStruct release and installs it after you confirm.

.DESCRIPTION
  Nothing runs in the background and nothing is installed without your answer.

  1. Reads the latest stable release (no pre-releases) and shows the active and the new version.
  2. Asks before downloading.
  3. Downloads the wheel and SHA256SUMS.txt and verifies the checksum.
  4. Installs the new version into its own folder (v<version>) next to the old one.
  5. Checks it: import, command line, MCP server (initialize, tools/list, tools/call).
  6. Only then switches "current" to it. The old version stays on disk for rollback.

  If any step fails, the active version is not changed.

      update-windows.cmd              check, ask, update
      update-windows.cmd -Check       only show whether an update exists
      update-windows.cmd -Rollback    switch back to the previously active version
      update-windows.cmd -List        show installed versions

.PARAMETER Yes
  Do not ask; answer yes. For scripts.

.PARAMETER ReleaseDir
  Use a local folder instead of GitHub (release.json with tag_name, the wheel and
  SHA256SUMS.txt). For offline installs and tests.
#>
param(
    [string]$Root = "",
    [string]$Repo = "KelesogluMustafa/pdfstruct",
    [switch]$Check,
    [switch]$Rollback,
    [switch]$List,
    [switch]$Yes,
    [string]$ReleaseDir = "",
    [string]$Installer = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "runtime-common.ps1")

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host "Nothing was changed: the active version is still $(Show-Version (Get-ActiveVersion $Root))."
    exit 1
}

function Show-Version($Value) { if ($Value) { return $Value } else { return "none" } }

$Root = Get-PdfstructRoot $Root
if (-not $Installer) { $Installer = Join-Path $PSScriptRoot "install-windows.ps1" }
$active = Get-ActiveVersion $Root

# ---------- list ----------
if ($List) {
    Write-Host "PDFStruct versions in $Root"
    foreach ($version in (Get-InstalledVersions $Root)) {
        $mark = ""
        if ($version -eq $active) { $mark = "  (active)" }
        elseif ($version -eq (Get-PreviousVersion $Root)) { $mark = "  (previous)" }
        Write-Host "  $version$mark"
    }
    exit 0
}

# ---------- rollback ----------
if ($Rollback) {
    $previous = Get-PreviousVersion $Root
    if (-not $previous) { Fail "there is no recorded previous version to go back to." }
    if ($previous -eq $active) { Fail "the previous version ($previous) is already active." }
    $python = Join-Path $Root "v$previous\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { Fail "the previous version $previous is no longer installed." }
    & $python -c "import pdfstruct, sys; sys.exit(0 if pdfstruct.__version__ == '$previous' else 1)"
    if ($LASTEXITCODE -ne 0) { Fail "the previous version $previous does not start." }
    try { Set-ActiveVersion $Root $previous | Out-Null } catch { Fail $_.Exception.Message }
    Write-Host "Rolled back: PDFStruct $previous is active again (was $(Show-Version $active))." -ForegroundColor Green
    Write-Host "Restart Claude so it starts the active version."
    exit 0
}

# ---------- what is the latest stable release ----------
Write-Host "PDFStruct update"
Write-Host "  installed in: $Root"
Write-Host "  active:       $(Show-Version $active)"
try {
    if ($ReleaseDir) {
        $release = Get-Content -LiteralPath (Join-Path $ReleaseDir "release.json") -Raw | ConvertFrom-Json
    } else {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        # /releases/latest never returns drafts or pre-releases
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ "User-Agent" = "pdfstruct-updater" }
    }
} catch {
    Fail "could not read the latest release: $($_.Exception.Message)"
}
if ("$($release.tag_name)" -notmatch '^v(\d+\.\d+\.\d+)$') { Fail "unexpected release tag: $($release.tag_name)" }
$latest = $Matches[1]
Write-Host "  latest:       $latest"

if ($active -and ([version]$latest -le [version]$active)) {
    Write-Host ""
    Write-Host "PDFStruct is up to date."
    exit 0
}
if ($Check) {
    Write-Host ""
    Write-Host "An update is available: $(Show-Version $active) -> $latest. Run update-windows.cmd to install it."
    exit 0
}

# ---------- ask ----------
Write-Host ""
Write-Host "Update available: $(Show-Version $active) -> $latest"
Write-Host "It is installed next to the current version; the current one is kept for rollback."
if (-not $Yes) {
    Write-Host -NoNewline "Download and install it now? [y/N] "
    $answer = [Console]::In.ReadLine()
    if ("$answer".Trim().ToLower() -notin @("y", "yes", "e", "evet", "j", "ja")) {
        Write-Host "Cancelled. Nothing was downloaded or changed."
        exit 0
    }
}

# ---------- download the wheel and its checksum ----------
$wheelName = "pdfstruct-$latest-py3-none-any.whl"
$download = Join-Path $Root "releases\v$latest"
New-Item -ItemType Directory -Force -Path $download | Out-Null
$wheel = Join-Path $download $wheelName
$sums = Join-Path $download "SHA256SUMS.txt"
try {
    foreach ($name in @($wheelName, "SHA256SUMS.txt")) {
        $destination = Join-Path $download $name
        if ($ReleaseDir) {
            $source = Join-Path $ReleaseDir $name
            if (-not (Test-Path -LiteralPath $source)) { throw "the release has no $name" }
            Copy-Item -LiteralPath $source -Destination $destination -Force
        } else {
            $asset = $release.assets | Where-Object { $_.name -eq $name } | Select-Object -First 1
            if (-not $asset) { throw "the release has no $name" }
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $destination -UseBasicParsing -Headers @{ "User-Agent" = "pdfstruct-updater" }
        }
    }
} catch {
    Fail "download failed: $($_.Exception.Message)"
}

# ---------- the checksum is mandatory for an update ----------
$expected = $null
foreach ($line in Get-Content -LiteralPath $sums) {
    if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+)$' -and $Matches[2].Trim() -eq $wheelName) { $expected = $Matches[1].ToLower() }
}
$actual = (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLower()
if (-not $expected -or $actual -ne $expected) {
    Remove-Item -LiteralPath $wheel -Force
    if (-not $expected) { Fail "SHA256SUMS.txt does not list $wheelName; the download was deleted." }
    Fail "checksum mismatch for $wheelName; the download was deleted."
}
Write-Host "  checksum: OK ($($actual.Substring(0, 16))...)"

# ---------- install, check, activate (the installer switches only after its checks pass) ----------
& powershell -NoProfile -ExecutionPolicy Bypass -File $Installer -Wheel $wheel -Root $Root
if ($LASTEXITCODE -ne 0) {
    Fail "the new version $latest could not be installed or did not pass its checks."
}
if ((Get-ActiveVersion $Root) -ne $latest) { Fail "the installer finished but $latest is not active." }

Write-Host ""
Write-Host "Updated: PDFStruct $latest is active." -ForegroundColor Green
if ($active) { Write-Host "Kept for rollback: $active   (update-windows.cmd -Rollback)" }
Write-Host ""
Write-Host "Claude:"
Write-Host "  - Restart Claude (Code and Desktop) so it starts the new version."
Write-Host "  - The plugin and the .mcpb extension start the 'current' runtime; they do not need to be"
Write-Host "    reinstalled for this update. Reinstall pdfstruct-plugin.zip or the .mcpb only when the"
Write-Host "    release notes of $latest say that the plugin, the skill or the extension changed."
exit 0
