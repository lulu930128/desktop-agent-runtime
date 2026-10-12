Option Explicit

Dim sh, shellApp, fso
Dim repoRoot, launcherScript, pythonwExe, pythonExe
Dim launcherArgs, cmd

Set sh = CreateObject("WScript.Shell")
Set shellApp = CreateObject("Shell.Application")
Set fso = CreateObject("Scripting.FileSystemObject")

repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
launcherScript = fso.BuildPath(repoRoot, "launcher_qt.py")
pythonwExe = fso.BuildPath(repoRoot, "envs\kuro-llm310\pythonw.exe")
pythonExe = fso.BuildPath(repoRoot, "envs\kuro-llm310\python.exe")
launcherArgs = """" & launcherScript & """"

sh.CurrentDirectory = repoRoot

If WScript.Arguments.Named.Exists("check") Then
    WScript.Quit 0
End If

If Not fso.FileExists(launcherScript) Then
    Call MsgBox("Kuro launcher was not found: " & launcherScript, vbCritical, "Kuro")
    WScript.Quit 2
End If

If fso.FileExists(pythonwExe) Then
    shellApp.ShellExecute pythonwExe, launcherArgs, repoRoot, "open", 1
ElseIf fso.FileExists(pythonExe) Then
    cmd = """" & pythonExe & """ " & launcherArgs
    sh.Run cmd, 0, False
Else
    Call MsgBox("Kuro Python was not found: " & pythonwExe, vbCritical, "Kuro")
    WScript.Quit 2
End If
