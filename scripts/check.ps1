$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)" }
}
Invoke-Checked '.venv/Scripts/python.exe' @('-m', 'ruff', 'check', '.')
Invoke-Checked '.venv/Scripts/python.exe' @('-m', 'ruff', 'format', '--check', '.')
Invoke-Checked '.venv/Scripts/python.exe' @('-m', 'pytest', '-q')
Invoke-Checked 'npm.cmd' @('run', 'check')
Invoke-Checked 'npm.cmd' @('run', 'test:e2e')
