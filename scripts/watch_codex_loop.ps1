#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [string]$EventPath = (Join-Path ([IO.Path]::GetTempPath()) 'codex-revops-loop-events.jsonl'),
    [string]$SeenPath = (Join-Path ([IO.Path]::GetTempPath()) 'codex-revops-loop-watcher-seen.json'),
    [ValidateRange(1, 60)]
    [int]$PollSeconds = 2,
    [switch]$NoNotify,
    [switch]$RunOnce,
    [switch]$TestNotification,
    [switch]$ReplayExisting
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$eventFile = [IO.Path]::GetFullPath($EventPath)
if ($eventFile.Equals($repoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $eventFile.StartsWith($repoRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The watcher event file must be outside the repository.'
}
$seenFile = [IO.Path]::GetFullPath($SeenPath)
if ($seenFile.Equals($repoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $seenFile.StartsWith($repoRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The watcher deduplication file must be outside the repository.'
}
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$hasSeenState = Test-Path -LiteralPath $seenFile
if ($hasSeenState) {
    try {
        $savedIds = Get-Content -LiteralPath $seenFile -Raw | ConvertFrom-Json
        foreach ($id in $savedIds) { [void]$seen.Add([string]$id) }
    }
    catch {
        Write-Warning 'Could not read watcher deduplication state; starting with an empty ID set.'
    }
}
elseif (-not $ReplayExisting -and (Test-Path -LiteralPath $eventFile)) {
    $ignoredCount = 0
    foreach ($line in (Get-Content -LiteralPath $eventFile -ErrorAction Stop)) {
        try { $oldEvent = $line | ConvertFrom-Json -ErrorAction Stop }
        catch { continue }
        $oldId = [string]$oldEvent.event_id
        if ($oldId -match '^[0-9a-fA-F-]{36}$' -and
            [string]$oldEvent.event_type -in @('halt', 'human_required', 'goal_achieved') -and
            [string]$oldEvent.source -in @('gate', 'supervisor')) {
            if ($seen.Add($oldId)) { $ignoredCount++ }
        }
    }
    if ($ignoredCount -gt 0) {
        $saved = @($seen | Select-Object -Last 500)
        $saved | ConvertTo-Json | Set-Content -LiteralPath $seenFile -Encoding utf8
        Write-Host "Ignored $ignoredCount pre-existing event(s); watching only for new events."
    }
}

function Send-LoopNotification {
    param(
        [Parameter(Mandatory)][ValidateSet('halt', 'human_required', 'goal_achieved')][string]$EventType,
        [Parameter(Mandatory)][AllowEmptyString()][string]$ItemText,
        [switch]$TestOnly
    )

    $title = switch ($EventType) {
        'goal_achieved' { 'Codex loop completed' }
        'human_required' { 'Codex loop requires attention' }
        default { 'Codex loop halted' }
    }
    $message = if ($ItemText) { "A loop event occurred. $ItemText" } else { 'A loop event occurred.' }
    if ($TestOnly) {
        $title = 'Codex loop watcher test'
        $message = 'Test notification only; no loop state was changed.'
    }
    if ($NoNotify) {
        Write-Host "NOTIFICATION MOCK: $title | $message"
        return
    }

    $icon = $null
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $icon = [System.Windows.Forms.NotifyIcon]::new()
        $icon.Icon = [System.Drawing.SystemIcons]::Warning
        $icon.Visible = $true
        $icon.BalloonTipTitle = $title
        $icon.BalloonTipText = $message
        $icon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning
        $icon.ShowBalloonTip(10000)
        [Console]::Beep(880, 180)
        if ($TestOnly) { Write-Host 'Watcher test notification requested.' }
        else { Write-Host "Notification requested for event type '$EventType'." }
        Start-Sleep -Seconds 10
    }
    catch {
        Write-Host "NOTIFICATION_DELIVERY_FAILED: $($_.Exception.GetType().Name)"
    }
    finally {
        if ($null -ne $icon) {
            $icon.Visible = $false
            $icon.Dispose()
        }
    }
}

Write-Host "Watching read-only loop events at: $eventFile"
Write-Host 'Press Ctrl+C to stop the watcher.'
if ($TestNotification) {
    Send-LoopNotification -EventType 'goal_achieved' -ItemText '' -TestOnly
    Write-Host 'Watcher notification smoke test finished.'
    exit 0
}
$lastHealth = [DateTimeOffset]::UtcNow
try {
while ($true) {
    if (Test-Path -LiteralPath $eventFile) {
        foreach ($line in (Get-Content -LiteralPath $eventFile -ErrorAction Stop)) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            try { $event = $line | ConvertFrom-Json -ErrorAction Stop }
            catch { continue }

            $eventId = [string]$event.event_id
            $eventType = [string]$event.event_type
            if ($eventId -notmatch '^[0-9a-fA-F-]{36}$' -or
                $eventType -notin @('halt', 'human_required', 'goal_achieved') -or
                [string]$event.source -notin @('gate', 'supervisor')) { continue }
            if (-not $seen.Add($eventId)) { continue }

            $itemText = ''
            $itemNumber = 0
            if ([int]::TryParse([string]$event.item_number, [ref]$itemNumber) -and $itemNumber -gt 0) {
                $itemText = "Item $itemNumber."
            }
            Send-LoopNotification -EventType $eventType -ItemText $itemText
            $saved = @($seen | Select-Object -Last 500)
            try { $saved | ConvertTo-Json | Set-Content -LiteralPath $seenFile -Encoding utf8 }
            catch { Write-Host "WATCHER_STATE_WRITE_FAILED: $($_.Exception.GetType().Name)" }
        }
    }

    if (([DateTimeOffset]::UtcNow - $lastHealth).TotalSeconds -ge 60) {
        Write-Host "Watcher healthy: $([DateTimeOffset]::UtcNow.ToString('u'))"
        $lastHealth = [DateTimeOffset]::UtcNow
    }
    if ($RunOnce) { break }
    Start-Sleep -Seconds $PollSeconds
}
}
finally {
    Write-Host 'Watcher stopped.'
}
