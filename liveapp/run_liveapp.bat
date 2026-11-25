@echo off
rem Start the live app (Windows). Add --source off when there is no internet.
cd /d "%~dp0.."
python liveapp\main.py %*
pause
