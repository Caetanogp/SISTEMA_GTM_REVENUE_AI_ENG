#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$Model = $env:CODEX_MODEL,
    [string]$ArchitectureModel = $env:CODEX_ARCHITECTURE_MODEL,
    [ValidateSet("low", "medium", "high", "xhigh")]
    [string]$ReasoningEffort = "medium",
    [ValidateSet("high", "xhigh")]
    [string]$ArchitectureReasoningEffort = "xhigh",
    [ValidateRange(1, 1000)]
    [int]$MaxTurns = 100,
    [ValidateRange(0, 20)]
    [int]$MaxProcessRetries = 2,
    [ValidateRange(0, 3600)]
    [int]$RetryDelaySeconds = 30,
    [switch]$UseLiveSearch
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-RepoPath {
    param([string]$Path)
    return (Resolve-Path $Path).Path
}

$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $PSCommandPath }
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $scriptRoot ".."
}

$repo = Get-RepoPath $RepoRoot
$requiredFiles = @(
    "AGENTS.md",
    ".handoff/STATE.md",
    ".handoff/AUTONOMOUS_QUEUE.md",
    "docs/playbooks/autonomous-loop.md",
    ".codex/prompts/autonomous-loop.md",
    "scripts/autonomous_gate.py",
    "scripts/codex_loop_supervisor.py"
)

foreach ($relativePath in $requiredFiles) {
    $fullPath = Join-Path $repo $relativePath
    if (-not (Test-Path $fullPath)) {
        throw "Missing required file for the Codex autonomous loop: $relativePath"
    }
}

$branch = (& git -C $repo rev-parse --abbrev-ref HEAD).Trim()
if ($branch -in @("main", "develop")) {
    throw "Refusing to launch the Codex autonomous loop on branch '$branch'. Use a feature branch."
}

$args = @(
    "-m", "scripts.codex_loop_supervisor",
    "--repo", $repo,
    "--implementation-effort", $ReasoningEffort,
    "--architecture-effort", $ArchitectureReasoningEffort,
    "--max-turns", $MaxTurns,
    "--max-process-retries", $MaxProcessRetries,
    "--retry-delay-seconds", $RetryDelaySeconds
)

if ($Model) {
    $args += @("--implementation-model", $Model)
}

if ($ArchitectureModel) {
    $args += @("--architecture-model", $ArchitectureModel)
}

if ($UseLiveSearch) {
    $args += "--search"
}

# Keep each loop's pytest files outside the checkout. The shared .pytest_cache path may be a
# OneDrive reparse point, and pytest's fallback directory can pollute the checkout during mypy.
$pytestBaseTemp = Join-Path $env:TEMP ("codex-revops-pytest-{0}" -f $PID)
New-Item -ItemType Directory -Force -Path $pytestBaseTemp | Out-Null
$env:TEMP = $pytestBaseTemp
$env:TMP = $pytestBaseTemp
$env:PYTEST_ADDOPTS = "--basetemp=$pytestBaseTemp"

Push-Location $repo
try {
    & python @args
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $exitCode
