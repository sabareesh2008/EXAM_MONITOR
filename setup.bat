@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Setup finished. Edit .env before starting VSB Exam Watch.
pause
