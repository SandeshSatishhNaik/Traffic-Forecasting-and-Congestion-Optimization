@echo off
rem One-time setup of the live app on Windows: packages, data, trained models.
cd /d "%~dp0.."
python -m pip install --upgrade fastapi uvicorn pandas numpy scikit-learn torch
python liveapp\sync.py
if defined TOMTOM_API_KEY python liveapp\sync.py --geometry
python liveapp\train.py
pause
