@echo off
REM AI Usage Overlay を起動。探索順: py ランチャー → PATH の pythonw → 既定インストール先
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw -3 "%~dp0badge.py" & exit /b)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0badge.py" & exit /b)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "C:\Python3*") do (
  if exist "%%~D\pythonw.exe" (start "" "%%~D\pythonw.exe" "%~dp0badge.py" & exit /b)
)
echo Python 3.9 以降が見つかりません。python.org からインストールし、
echo 「Add python.exe to PATH」にチェックを入れてから再実行してください。
pause
exit /b 1
