@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\show_simulation.ps1" -View workspace
if errorlevel 1 pause
