# Sync edits into the installed Claude Code plugin.
#
# The plugin cache is VERSION-PINNED: editing skill files does nothing until the
# version in plugin.json changes AND the plugin is reinstalled. This script does
# the whole dance:
#
#   validate -> bump patch version -> refresh marketplace -> reinstall -> verify
#
# Usage:  powershell -ExecutionPolicy Bypass -File build\sync.ps1
#
# NOTE: plugin.json must be written WITHOUT a byte-order mark. PowerShell 5.1's
# `Set-Content -Encoding utf8` emits a BOM, which makes Claude Code fail with
# "JSON parse error: Unrecognized token". We use .NET UTF8Encoding($false) instead.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Write-JsonNoBom($path, $obj) {
    $json = ($obj | ConvertTo-Json -Depth 10)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $json + "`n", $utf8NoBom)
}

# 1. Validate before touching anything installed
Write-Host "[1/5] Validating..." -ForegroundColor Cyan
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction Stop }
& $py.Source (Join-Path $root 'build\validate.py')
if ($LASTEXITCODE -ne 0) { throw "Validation failed - nothing was installed." }

# 2. Bump the patch version
$manifestPath = Join-Path $root 'plugins\shopify-clone-kit\.claude-plugin\plugin.json'
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$parts = $manifest.version.Split('.')
$parts[2] = [int]$parts[2] + 1
$newVersion = $parts -join '.'
$manifest.version = $newVersion
Write-JsonNoBom $manifestPath $manifest
Write-Host "[2/5] Version -> $newVersion" -ForegroundColor Cyan

# 3. Refresh the marketplace so it sees the new manifest
Write-Host "[3/5] Refreshing marketplace..." -ForegroundColor Cyan
claude plugin marketplace update shopify-clone-kit | Out-Host

# 4. Reinstall. `plugin update` resolves the version to "unknown" for local
#    marketplaces, leaving a junk cache dir - uninstall/install is reliable.
Write-Host "[4/5] Reinstalling plugin..." -ForegroundColor Cyan
# Uninstall is best-effort: a not-installed plugin is a fine starting state.
# Do NOT use `2>&1` on a native exe here - in PS 5.1 that wraps stderr lines in
# ErrorRecords and trips $ErrorActionPreference='Stop' even on success.
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
claude plugin uninstall shopify-clone-kit@shopify-clone-kit | Out-Host
$ErrorActionPreference = $prev

$cacheRoot = Join-Path $env:USERPROFILE '.claude\plugins\cache\shopify-clone-kit'
if (Test-Path $cacheRoot) { Remove-Item $cacheRoot -Recurse -Force }
claude plugin install shopify-clone-kit@shopify-clone-kit | Out-Host

# 5. Verify the cache actually moved
Write-Host "[5/5] Verifying installed cache..." -ForegroundColor Cyan
$cache = Join-Path $cacheRoot "shopify-clone-kit\$newVersion"
if (Test-Path (Join-Path $cache 'skills')) {
    $n = (Get-ChildItem (Join-Path $cache 'skills') -Directory).Count
    Write-Host "OK - $n skill(s) live at version $newVersion" -ForegroundColor Green
} else {
    Write-Warning "Cache for $newVersion not found under $cacheRoot - check 'claude plugin list'."
}

Write-Host ""
Write-Host "Restart Claude Code (or start a new session) to load the changes."
