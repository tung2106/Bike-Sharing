$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Output 'Chua cai dat. Chay setup.ps1 truoc.'
    exit 1
}
& $pythonPath open_website.py
