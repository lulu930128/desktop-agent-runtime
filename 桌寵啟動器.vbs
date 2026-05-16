Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ""Set-Location '" & Replace(repoRoot, "'", "''") & "'; py .\launcher.py"""
sh.Run cmd, 0, False
