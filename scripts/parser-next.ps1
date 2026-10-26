param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Output,
    [int]$TimeoutSeconds = 1800
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:MINERU_HOME = Join-Path (Get-Location) '.local/parser-next/mineru-home'
$env:HF_HOME = Join-Path (Get-Location) '.local/parser-next/huggingface'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = (Get-Location).Path
# Timeout and cancellation are managed by the wrapper; documents stay local.
& .venv/Scripts/python.exe -m backend.parsing_next.runner $Source $Output --timeout $TimeoutSeconds
if ($LASTEXITCODE -ne 0) { throw "Parser exited with code $LASTEXITCODE" }
