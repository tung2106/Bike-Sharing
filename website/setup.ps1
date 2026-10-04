$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Can cai Python 3.12 hoac 3.13 truoc.' }
}
& $pythonPath -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Cai thu vien that bai.' }
Write-Output 'Da cai dat. Chay ./start.ps1, sau do mo http://127.0.0.1:8000'
