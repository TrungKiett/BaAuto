@echo off
setlocal EnableDelayedExpansion
title Web Automator Studio - Build Tool

echo.
echo ===================================================
echo   Web Automator Studio - Build Desktop App (.exe)
echo ===================================================
echo.

REM Kiem tra Python venv
if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Khong tim thay .venv\Scripts\python.exe
    echo Hay chay: python -m venv .venv
    echo Sau do:   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

set PYTHON=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip

echo [1/5] Kiem tra va cai PyInstaller...
%PIP% install pyinstaller --quiet
if errorlevel 1 (
    echo [LOI] Khong the cai PyInstaller!
    pause
    exit /b 1
)
echo      OK

echo.
echo [2/5] Doc version hien tai...
for /f "delims=" %%v in ('%PYTHON% -c "from version import VERSION; print(VERSION)"') do set VERSION=%%v
echo      Version: v%VERSION%

echo.
echo [3/5] Don dep build cu (neu co)...
if exist "dist\WebAutomatorStudio.exe" (
    del /q "dist\WebAutomatorStudio.exe"
    echo      Da xoa dist\WebAutomatorStudio.exe cu
)
if exist "build" rmdir /s /q build
if exist "WebAutomatorStudio.spec" del /q "WebAutomatorStudio.spec"
echo      OK

echo.
echo [4/5] Build .exe voi PyInstaller...
echo      (Co the mat 2-5 phut, vui long cho...)
echo.

%PYTHON% -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --name "WebAutomatorStudio" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --collect-all playwright ^
    --collect-submodules google.genai ^
    --collect-submodules anthropic ^
    --hidden-import=flask ^
    --hidden-import=flask.templating ^
    --hidden-import=jinja2 ^
    --hidden-import=ai_providers ^
    --hidden-import=ai_agent ^
    --hidden-import=updater ^
    --hidden-import=version ^
    --hidden-import=automator ^
    --hidden-import=google.genai ^
    --hidden-import=openai ^
    --hidden-import=anthropic ^
    --hidden-import=requests ^
    --hidden-import=PIL ^
    --noconfirm ^
    app.py

if errorlevel 1 (
    echo.
    echo [LOI] Build that bai! Xem log ben tren de biet nguyen nhan.
    pause
    exit /b 1
)

echo.
echo [5/5] Kiem tra ket qua...
if exist "dist\WebAutomatorStudio.exe" (
    for %%A in ("dist\WebAutomatorStudio.exe") do set SIZE=%%~zA
    set /a SIZE_MB=!SIZE! / 1048576
    echo.
    echo ===================================================
    echo   BUILD THANH CONG!
    echo ===================================================
    echo.
    echo   File:    dist\WebAutomatorStudio.exe
    echo   Version: v%VERSION%
    echo   Size:    ~!SIZE_MB! MB
    echo.
    echo   De phat hanh:
    echo   1. Tao GitHub Release voi tag "v%VERSION%"
    echo   2. Upload file dist\WebAutomatorStudio.exe
    echo   3. Nguoi dung co the cap nhat tu dong!
    echo.
) else (
    echo [LOI] Khong tim thay file .exe sau khi build!
)

pause
