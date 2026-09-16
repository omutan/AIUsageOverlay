' スタートアップに登録（PC起動時に自動表示）。解除は remove_autostart.vbs
Dim sh, fso, dir, startup, lnk, sc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
startup = sh.SpecialFolders("Startup")
lnk = startup & "\AIUsageOverlay.lnk"
Set sc = sh.CreateShortcut(lnk)
sc.TargetPath = "wscript.exe"
sc.Arguments = """" & dir & "\start.vbs"""
sc.WorkingDirectory = dir
sc.Save
MsgBox "スタートアップに登録しました。" & vbCrLf & lnk, 64, "AI Usage Overlay"
