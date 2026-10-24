
@echo off
title AttendIQ Launcher

set "PROJECT=C:\Users\DELL\Desktop\PROJECTS\AttendIQ_By_Mayank\AttendIQ"
set "PYTHON=C:\Users\DELL\anaconda3\envs\attendiq\python.exe"

cd /d "%PROJECT%"

if not exist "%PYTHON%" (
    echo ERROR: AttendIQ Python path not found.
    echo Please check the Python path in this file.
    pause
    exit /b 1
)

echo Starting AttendIQ...
"%PYTHON%" -c "import flask; print('Flask OK')"

if errorlevel 1 (
    echo Flask is missing from this environment.
    pause
    exit /b 1
)

start "" http://127.0.0.1:5000
"%PYTHON%" app.py

pause
