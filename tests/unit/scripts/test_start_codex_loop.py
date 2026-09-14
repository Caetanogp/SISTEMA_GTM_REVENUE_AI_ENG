from __future__ import annotations

from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[3] / "scripts" / "start_codex_loop.ps1"


def test_launcher_uses_explicit_external_temp_root() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert (
        '$codexTempRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData"))'
        in source
    )
    assert '"Codex\\Temp"' in source
    assert "$pytestBaseTemp = Join-Path $codexTempRoot" in source
    assert "$pytestBaseTemp = Join-Path $env:TEMP" not in source
