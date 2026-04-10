@echo off
setlocal
cd /d "%~dp0"

set "CREATED="
if not exist ".venv\Scripts\python.exe" (
  echo No .venv found — creating virtual environment...
  python -m venv .venv
  if errorlevel 1 exit /b 1
  set CREATED=1
)

call ".venv\Scripts\activate.bat"

if defined CREATED (
  echo Installing dependencies...
  pip install -r requirements.txt
)
pip install -r requirements.txt

if not exist "db.sqlite3" (
  echo Running migrate...
  python manage.py migrate
)

echo Starting server at http://127.0.0.1:8000/ ^(Ctrl+C to stop^)
python manage.py runserver 0.0.0.0:8000
