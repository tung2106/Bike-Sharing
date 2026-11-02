@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
title Bike Rental - Random Forest - 8000
if not exist "website\.venv\Scripts\python.exe" (
    echo Chua co moi truong Python. Hay chay website\setup.ps1 truoc.
    pause
    exit /b 1
)
"website\.venv\Scripts\python.exe" -B "website\open_model.py" rf
if errorlevel 1 (
    echo.
    echo Khong mo duoc web. Xem loi phia tren. Khong tu tat may chu dang chiem cong.
    pause
)
