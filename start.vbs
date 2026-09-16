' AI Usage Overlay - コンソール非表示で起動（Pythonは PATH の pythonw を使用）
Dim sh, fso, dir
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
sh.Run "pythonw """ & dir & "\badge.py""", 0, False
Set sh = Nothing
