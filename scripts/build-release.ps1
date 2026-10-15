param([switch]$SkipChecks)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)" }
}
if (-not $SkipChecks) { & "$PSScriptRoot/check.ps1" }
Invoke-Checked '.venv/Scripts/python.exe' @('scripts/prepare_release.py')
Invoke-Checked 'npm.cmd' @('run', 'build')
if (-not $env:ELECTRON_BUILDER_COMPRESSION_LEVEL) { $env:ELECTRON_BUILDER_COMPRESSION_LEVEL = '3' }
Invoke-Checked 'npx.cmd' @('electron-builder', '--win', 'nsis', '--x64')
Get-ChildItem -LiteralPath 'dist' -Filter '*Setup.exe' | ForEach-Object {
    $digest = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    Set-Content -LiteralPath ($_.FullName + '.sha256') -Value ($digest.Hash.ToLower() + '  ' + $_.Name)
}
