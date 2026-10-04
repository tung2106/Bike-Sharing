@echo off
setlocal
cd /d "%~dp0"
title Velo - Du doan luot thue xe
if not exist "website\.venv\Scripts\python.exe" (
    echo Chua co moi truong Python cua website.
    echo Hay cai dat theo website\HUONG_DAN.txt truoc khi mo.
    pause
    exit /b 1
)
"website\.venv\Scripts\python.exe" "website\open_website.py"
if errorlevel 1 (
    echo.
    echo Khong mo duoc website. Xem thong bao phia tren.
    pause
)
