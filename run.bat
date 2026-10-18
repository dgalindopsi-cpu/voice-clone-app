@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo No se encontro el entorno virtual. Sigue las instrucciones del README.md.
  pause
  exit /b 1
)
"venv\Scripts\python.exe" main.py
pause
