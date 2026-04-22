<#
.SYNOPSIS
    Deploy an OpenClaw skill from this repo to the user's OpenClaw workspace.

.DESCRIPTION
    OpenClaw refuses to load skill directories reached via junction / symlink
    (security: reason=symlink-escape). So we maintain the source in this repo
    and copy into ~/.openclaw/workspace/skills/<SkillName>/ whenever it changes.

    Dev-only directories are excluded to keep the deployed copy clean:
        state/              runtime session JSON
        tests/              pytest suites
        __pycache__/        Python bytecode
        .pytest_cache/      pytest state

.PARAMETER SkillName
    Name of the skill folder under ./skills/. Required.

.PARAMETER WhatIf
    Dry run. Show what would be copied without touching the workspace.

.EXAMPLE
    .\tools\deploy-skill.ps1 auction_king

.EXAMPLE
    .\tools\deploy-skill.ps1 csv_analyzer -WhatIf
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$SkillName
)

$ErrorActionPreference = "Stop"

# Resolve source (this repo) and target (OpenClaw workspace).
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Source   = Join-Path $RepoRoot "skills\$SkillName"
$Target   = Join-Path $env:USERPROFILE ".openclaw\workspace\skills\$SkillName"

if (-not (Test-Path $Source)) {
    Write-Error "Source skill folder not found: $Source"
    exit 1
}

Write-Host ""
Write-Host "Deploying skill:" -ForegroundColor Cyan
Write-Host "  Source: $Source"
Write-Host "  Target: $Target"
Write-Host ""

# If target exists and is a junction/symlink, delete just the link.
# Otherwise delete the whole directory.
if (Test-Path $Target) {
    $item = Get-Item $Target -Force
    if ($item.LinkType -in @("Junction", "SymbolicLink")) {
        Write-Host "Target is a $($item.LinkType); removing link..." -ForegroundColor Yellow
        if ($PSCmdlet.ShouldProcess($Target, "Remove junction/symlink")) {
            Remove-Item $Target -Force
        }
    } else {
        Write-Host "Target exists; removing previous copy..." -ForegroundColor Yellow
        if ($PSCmdlet.ShouldProcess($Target, "Remove directory recursively")) {
            Remove-Item $Target -Recurse -Force
        }
    }
}

# robocopy exit codes 0-7 are success (files copied / no change / extra).
# 8+ are real errors.
$RoboArgs = @(
    $Source,
    $Target,
    "/E",
    "/XD", "state", "__pycache__", ".pytest_cache", "tests",
    "/NFL", "/NDL", "/NJH", "/NJS"
)

if ($PSCmdlet.ShouldProcess($Target, "robocopy from $Source")) {
    & robocopy @RoboArgs | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        Write-Error "robocopy failed with exit code $rc"
        exit $rc
    }
    Write-Host "robocopy finished (exit=$rc, 0-7 means success)." -ForegroundColor Green
} else {
    Write-Host "(WhatIf) robocopy $Source -> $Target" -ForegroundColor Gray
    exit 0
}

Write-Host ""
Write-Host "Deployed files:" -ForegroundColor Cyan
Get-ChildItem $Target | Select-Object Mode, LastWriteTime, Name | Format-Table -AutoSize

Write-Host "Next step:" -ForegroundColor Cyan
Write-Host "  1. Restart gateway:  Ctrl+C in the gateway window, then re-run ``openclaw gateway``"
Write-Host "  2. Verify loaded:    ``openclaw skills list | Select-String $SkillName``"
Write-Host "                       expect -> '+ ready ... $SkillName ... openclaw-workspace'"
Write-Host ""
