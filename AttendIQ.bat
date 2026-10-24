@echo off
title AttendIQ - Attendance System
color 0A

set PROJECT=C:\Users\HP\Downloads\Face-Recognition-Based-Attendance-System-main\Face-Recognition-Based-Attendance-System-main
set CONDA=C:\Users\HP\miniconda3

echo.
echo  =========================================
echo   AttendIQ - Face Attendance System
echo  =========================================
echo.

:: Activate conda environment
call "%CONDA%\Scripts\activate.bat" attendance

cd /d "%PROJECT%"

echo  Choose an option:
echo.
echo  [1] Mark Attendance (Camera)
echo  [2] Register New Student (Camera)
echo  [3] Open Dashboard (Web)
echo  [4] Full Start (Attendance + Dashboard)
echo  [5] Exit
echo.
set /p choice= Enter your choice (1-5):

if "%choice%"=="1" goto attendance
if "%choice%"=="2" goto register
if "%choice%"=="3" goto dashboard
if "%choice%"=="4" goto full
if "%choice%"=="5" exit

:attendance
echo.
echo  Starting attendance camera...
echo  Press Q to quit camera when done.
echo.
python attendance_taker.py
echo.
echo  Attendance marked! Opening dashboard...
timeout /t 2 >nul
start http://127.0.0.1:5000
python app.py
goto end

:register
echo.
echo  Opening student registration...
echo  Enter name, click Input, then Save Current Face multiple times.
echo.
python get_faces_from_camera_tkinter.py
echo.
echo  Registration done! Now extracting features...
python features_extraction_to_csv.py
echo.
echo  Done! Student registered successfully.
pause
goto end

:dashboard
echo.
echo  Opening dashboard...
start http://127.0.0.1:5000
python app.py
goto end

:full
echo.
echo  Step 1: Starting attendance camera...
echo  Press Q when done marking attendance.
echo.
python attendance_taker.py
echo.
echo  Step 2: Opening dashboard...
start http://127.0.0.1:5000
python app.py
goto end

:end
pause
