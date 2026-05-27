Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe = fso.BuildPath(repoRoot, "envs\kuro-llm310\python.exe")

If fso.FileExists(pythonExe) Then
    cmd = "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ""Set-Location -LiteralPath '" & Replace(repoRoot, "'", "''") & "'; & '" & Replace(pythonExe, "'", "''") & "' .\launcher.py"""
Else
    cmd = "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ""Set-Location -LiteralPath '" & Replace(repoRoot, "'", "''") & "'; py .\launcher.py"""
End If
sh.Run cmd, 0, False
