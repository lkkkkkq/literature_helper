$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)" }
}
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    Invoke-Checked 'python' @('-m', 'venv', '.venv')
}
Invoke-Checked '.venv/Scripts/python.exe' @('-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple', '-r', 'requirements.lock')
Invoke-Checked '.venv/Scripts/python.exe' @('-m', 'pip', 'install', '--no-deps', '--no-build-isolation', '-e', '.')
Invoke-Checked 'npm.cmd' @('ci')
Invoke-Checked 'node' @('node_modules/electron/install.js')
Write-Host 'Setup complete. Start with: npm run dev'
