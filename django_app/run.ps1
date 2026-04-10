# Quick start: activate .venv (create if missing) and run Django dev server.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$createdVenv = $false
if (-not (Test-Path $venvPy)) {
    Write-Host "No .venv found — creating virtual environment..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $createdVenv = $true
}

. (Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1")

if ($createdVenv) {
    $req = Join-Path $PSScriptRoot "requirements.txt"
    if (Test-Path $req) {
        Write-Host "Installing dependencies..."
        pip install -r $req
    }
}

$db = Join-Path $PSScriptRoot "db.sqlite3"
if (-not (Test-Path $db)) {
    Write-Host "Running migrate..."
    python manage.py migrate
}

Write-Host "Starting server at http://127.0.0.1:8000/ (Ctrl+C to stop)"
python manage.py runserver
