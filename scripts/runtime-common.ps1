# Shared by install-windows.ps1 and update-windows.ps1 (dot-sourced).
#
# Layout under the root (default %USERPROFILE%\.local\pdfstruct):
#   v<version>\              one private Python environment per installed version
#   current                  directory junction to the active version; Claude starts
#                            current\Scripts\pdfstruct-mcp.exe, so no path names a version
#   previous-version.txt     the version that was active before the last switch (for rollback)
#
# The junction is only ever switched after the new runtime passed verify_runtime.py.

function Get-PdfstructRoot([string]$Root) {
    if ($Root) { return $Root }
    return (Join-Path $HOME ".local\pdfstruct")
}

function Test-Junction([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $item = Get-Item -LiteralPath $Path -Force
    return [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

# The active version ("0.2.1") or $null. Read from the junction target, never guessed.
function Get-ActiveVersion([string]$Root) {
    $current = Join-Path $Root "current"
    if (-not (Test-Junction $current)) { return $null }
    $target = (Get-Item -LiteralPath $current -Force).Target
    if ($target -is [array]) { $target = $target[0] }
    if (-not $target) { return $null }
    $leaf = Split-Path -Leaf $target
    if ($leaf -match '^v(\d+\.\d+\.\d+)$') { return $Matches[1] }
    return $null
}

function Get-InstalledVersions([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root)) { return @() }
    $found = @()
    foreach ($dir in Get-ChildItem -LiteralPath $Root -Directory) {
        if ($dir.Name -match '^v(\d+\.\d+\.\d+)$' -and (Test-Path -LiteralPath (Join-Path $dir.FullName "Scripts\python.exe"))) {
            $found += $Matches[1]
        }
    }
    return @($found | Sort-Object { [version]$_ })
}

# Point "current" at v<Version>. Returns the version that was active before (or $null).
# Removes only the junction itself (rmdir on a junction never touches the target folder).
function Set-ActiveVersion([string]$Root, [string]$Version) {
    $target = Join-Path $Root "v$Version"
    if (-not (Test-Path -LiteralPath (Join-Path $target "Scripts\python.exe"))) {
        throw "version $Version is not installed at $target"
    }
    $current = Join-Path $Root "current"
    $before = Get-ActiveVersion $Root
    if ($before -eq $Version) { return $before }
    if (Test-Path -LiteralPath $current) {
        if (-not (Test-Junction $current)) { throw "$current exists and is not a junction; it was left untouched" }
        cmd /c rmdir "$current" | Out-Null
        if (Test-Path -LiteralPath $current) { throw "could not remove the old junction $current" }
    }
    cmd /c mklink /J "$current" "$target" | Out-Null
    if ((Get-ActiveVersion $Root) -ne $Version) {
        if ($before) { cmd /c mklink /J "$current" (Join-Path $Root "v$before") | Out-Null }
        throw "could not point $current at $target"
    }
    if ($before) {
        Set-Content -LiteralPath (Join-Path $Root "previous-version.txt") -Value $before -Encoding ASCII
    }
    return $before
}

function Get-PreviousVersion([string]$Root) {
    $file = Join-Path $Root "previous-version.txt"
    if (-not (Test-Path -LiteralPath $file)) { return $null }
    $value = (Get-Content -LiteralPath $file -TotalCount 1).Trim()
    if ($value -match '^\d+\.\d+\.\d+$') { return $value }
    return $null
}
