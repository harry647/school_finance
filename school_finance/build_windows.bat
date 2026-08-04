@echo off
REM ============================================================
REM  Build a standalone SchoolFinance.exe (no Python needed to run it)
REM  Run this ON WINDOWS, from inside the school_finance folder.
REM
REM  This script looks for Python 3.8 first (needed if the exe must run
REM  on Windows 7/8 machines), and falls back to whatever "python" is on
REM  your PATH if 3.8 isn't found (fine if all target PCs are Win10/11).
REM
REM  To get Python 3.8:
REM  https://www.python.org/downloads/release/python-3810/
REM  (Windows x86-64 executable installer) - install it WITHOUT adding
REM  it to PATH, so it doesn't interfere with any other Python you have.
REM ============================================================

setlocal enabledelayedexpansion
set PY=

REM 1) Try the Windows launcher's -3.8 flag (works if py.exe is installed)
py -3.8 --version >nul 2>&1
if %errorlevel%==0 (
    set PY=py -3.8
    goto found
)

REM 2) Try common default install locations for Python 3.8
for %%P in (
    "%LocalAppData%\Programs\Python\Python38\python.exe"
    "%LocalAppData%\Programs\Python\Python38-32\python.exe"
    "C:\Python38\python.exe"
) do (
    if exist %%P (
        set PY=%%~P
        goto found
    )
)

REM 3) Fall back to whatever "python" resolves to on PATH
echo Python 3.8 not found automatically - falling back to your default "python".
echo   (This is fine if EVERY PC you're deploying to is Windows 10 or 11.
echo    If any target PC is Windows 7 or 8, install Python 3.8 first - see
echo    the link at the top of this file - then run this script again.)
set PY=python

:found
echo Using: %PY%
%PY% --version

echo.
echo Installing required packages...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt

echo.
echo Building SchoolFinance.exe ...
%PY% -m PyInstaller --noconfirm --onefile --windowed ^
    --name SchoolFinance ^
    --add-data "db\schema.sql;db" ^
    --hidden-import=tkinter ^
    --hidden-import=reportlab.graphics.barcode.qr ^
    main.py

echo.
echo Checking for Visual C++ Redistributable (needed for Win 7/8)...
if not exist "vcredist" mkdir vcredist
if not exist "vcredist\vc_redist.x64.exe" (
    echo Downloading VC++ Redistributable...
    powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile 'vcredist\vc_redist.x64.exe' -UseBasicParsing" || echo WARNING: Failed to download VC++ redistributable. Download it manually from https://aka.ms/vs/17/release/vc_redist.x64.exe and place it in school_finance\vcredist\
) else (
    echo Found existing vcredist\vc_redist.x64.exe - skipping download.
)

echo.
echo ============================================================
echo Build complete. Your app is at: dist\SchoolFinance.exe
echo VC++ redistributable is at: vcredist\vc_redist.x64.exe
echo Next: open SchoolFinanceSetup.iss in Inno Setup and compile.
echo ============================================================
pause
