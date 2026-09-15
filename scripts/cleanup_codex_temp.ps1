#!/usr/bin/env pwsh

[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateRange(1, 3650)]
    [int]$OlderThanDays = 7,
    [switch]$ConfirmCleanup
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$tempRoot = [IO.Path]::GetFullPath(
    (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Codex\Temp")
).TrimEnd('\')
if (-not (Test-Path -LiteralPath $tempRoot -PathType Container)) {
    Write-Output "No Codex temp root exists: $tempRoot"
    exit 0
}

$cutoff = (Get-Date).AddDays(-$OlderThanDays)
$candidates = @(
    Get-ChildItem -LiteralPath $tempRoot -Directory -Force -ErrorAction Stop |
        Where-Object {
            $_.Name -like "codex-revops-*" -and $_.LastWriteTime -lt $cutoff
        }
)
if (-not $ConfirmCleanup) {
    $candidates | Select-Object FullName, LastWriteTime
    Write-Output "Dry run only. Re-run with -ConfirmCleanup to remove these exact directories."
    exit 0
}

foreach ($candidate in $candidates) {
    $resolved = (Resolve-Path -LiteralPath $candidate.FullName).Path.TrimEnd('\')
    if (-not $resolved.StartsWith("$tempRoot\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside Codex temp root: $resolved"
    }
    if ($candidate.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Refusing to remove reparse point: $resolved"
    }
    if ($PSCmdlet.ShouldProcess($resolved, "Remove stale Codex temporary directory")) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
