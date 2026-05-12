@echo off
title MKA Analyse App
echo.
echo  ==========================================
echo   MKA Analyse App wordt gestart...
echo   Sluit dit venster om de app te stoppen.
echo  ==========================================
echo.

REM Probeer python, dan python3
where python >nul 2>nul
if %errorlevel% == 0 (
    python "%~dp0start.py"
) else (
    where python3 >nul 2>nul
    if %errorlevel% == 0 (
        python3 "%~dp0start.py"
    ) else (
        echo.
        echo  FOUT: Python niet gevonden!
        echo  Installeer Python via https://python.org
        echo  Zorg dat je "Add Python to PATH" aanvinkt.
        echo.
        pause
    )
)
