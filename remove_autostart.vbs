' スタートアップ登録を解除
Dim sh, fso, startup, lnk
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
startup = sh.SpecialFolders("Startup")
lnk = startup & "\AIUsageOverlay.lnk"
If fso.FileExists(lnk) Then
  fso.DeleteFile lnk
  MsgBox "自動起動を解除しました。", 64, "AI Usage Overlay"
Else
  MsgBox "登録は見つかりませんでした。", 48, "AI Usage Overlay"
End If
