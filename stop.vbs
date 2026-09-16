' AI Usage Overlay を停止
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell -NoProfile -WindowStyle Hidden -Command ""Get-CimInstance Win32_Process | ? { $_.Name -match 'python' -and $_.CommandLine -like '*badge.py*' } | %% { Stop-Process -Id $_.ProcessId -Force }""", 0, False
Set sh = Nothing
