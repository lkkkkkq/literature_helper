$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed ($LASTEXITCODE)" }
}
New-Item -ItemType Directory -Force .local/parser-next | Out-Null
if (-not (Test-Path .local/parser-next/bootstrap/bin/uv.exe)) {
    Checked '.venv/Scripts/python.exe' @('-m','pip','install','--target','.local/parser-next/bootstrap','uv==0.13.5')
}
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.local/parser-next/python'
if (-not (Test-Path .local/parser-next/venv/Scripts/python.exe)) {
    Checked '.local/parser-next/bootstrap/bin/uv.exe' @('venv','--python','3.12.15','.local/parser-next/venv')
}
# The fixed set excludes DirectML: its shared namespace conflicted with ONNX Runtime.
Checked '.local/parser-next/bootstrap/bin/uv.exe' @('pip','install','--python','.local/parser-next/venv/Scripts/python.exe','--no-deps','-r','parser-next.requirements.lock')
$env:MINERU_HOME = Join-Path (Get-Location) '.local/parser-next/mineru-home'
$env:HF_HOME = Join-Path (Get-Location) '.local/parser-next/huggingface'
Checked '.local/parser-next/venv/Scripts/mineru-kit.exe' @('models','download','--tier','standard','--small-backend','onnx','--vlm-engine','llama-cpp','--source','huggingface')
Checked '.local/parser-next/venv/Scripts/mineru-kit.exe' @('models','verify','--tier','standard','--small-backend','onnx','--vlm-engine','llama-cpp')
Checked '.venv/Scripts/python.exe' @('scripts/collect_parser_notices.py')
