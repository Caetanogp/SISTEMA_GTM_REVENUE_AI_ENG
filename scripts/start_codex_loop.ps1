#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$Model = $env:CODEX_MODEL,
    [ValidateSet("read-only", "workspace-write", "danger-full-access")]
    [string]$SandboxMode = "workspace-write",
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
    "scripts/autonomous_gate.py"
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

$promptPath = Join-Path $repo ".codex/prompts/autonomous-loop.md"
$prompt = @"
Launch the Codex autonomous loop for this repository checkout.

Repository root: $repo
Current branch: $branch

This is a Codex session. Execute the queue directly in this Codex process. Do not launch Claude
Code, `claude`, `claude --bare`, or any other external coding agent or delegate the queue to one.
The user's normal Claude Code sessions in this repository are independent and must not be changed,
restarted, or inspected as part of this loop.

Read and follow AGENTS.md, .handoff/STATE.md, .handoff/AUTONOMOUS_QUEUE.md, and
docs/playbooks/autonomous-loop.md before making any change. Work the queue one item at a time in
order. Use scripts/autonomous_gate.py as the sole judge of done. Stop immediately on a HALT item
or when the gate exits 0.

$((Get-Content $promptPath -Raw).TrimEnd())
"@

$args = @(
    "exec",
    "--cd", $repo,
    "--approve-for-me"
)

if ($SandboxMode -ne "workspace-write") {
    $args += @("--sandbox", $SandboxMode)
}

if ($Model) {
    $args += @("--model", $Model)
}

if ($UseLiveSearch) {
    $args += "--search"
}

# Keep each loop's pytest files in a fresh ignored directory. The shared .pytest_cache path may
# be a OneDrive reparse point and can fail cleanup when multiple sessions use this checkout.
$pytestBaseTemp = Join-Path $repo ("scripts/.pytest_loop_temp_{0}" -f $PID)
New-Item -ItemType Directory -Force -Path $pytestBaseTemp | Out-Null
$env:PYTEST_ADDOPTS = "--basetemp=$pytestBaseTemp"

$prompt | & codex @args -
exit $LASTEXITCODE
