@echo off
chcp 65001 >nul
title Pinterest Video Downloader

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python не найден.
    echo Установите Python 3.10+ с сайта python.org
    echo и обязательно отметьте "Add Python to PATH".
    pause
    exit /b
)

if not exist ".venv\" (
    echo Создаём виртуальное окружение...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

start "" http://127.0.0.1:5000
python app.py
pause
