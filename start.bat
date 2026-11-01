@echo off
setlocal
cd /d "%~dp0"
if exist venv\Scripts\activate.bat (
  call venv\Scripts\activate.bat
) else if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
) else (
  echo Virtual environment not found. Run setup.bat first.
  pause
  exit /b 1
)
python main.py --dashboard
pause
