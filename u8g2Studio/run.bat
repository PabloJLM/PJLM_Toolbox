@echo off
rem u8g2 Studio - abre el explorador de carpetas si no le pasas una
cd /d "%~dp0"
if "%~1"=="" (
    python u8g2_studio.py
) else (
    python u8g2_studio.py "%~1"
)
if errorlevel 1 pause
