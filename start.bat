@echo off
REM AI Usage Overlay を起動（pythonw が無ければ python）
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw "%~dp0badge.py") || (start "" python "%~dp0badge.py")
