@echo off
rem Start the offline traffic app (Windows). Needs Python 3 and app\data\bundle.json.
cd /d "%~dp0.."
python app\server.py %*
pause
