param([string]$Python = "")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if ($Python) { & $Python -m venv .venv }
    else { py -3.12 -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Install it or run setup.ps1 -Python <python.exe path>.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& '.\.venv\Scripts\python.exe' -m pip install --no-deps --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw 'Application installation failed.' }
Write-Host 'Setup complete. Run run.bat to open AI Video to Sprite.'
