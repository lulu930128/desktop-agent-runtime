Set sh = CreateObject("WScript.Shell")
Set shellApp = CreateObject("Shell.Application")
Set fso = CreateObject("Scripting.FileSystemObject")
repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
launcherScript = fso.BuildPath(repoRoot, "launcher_qt.py")
pythonwExe = fso.BuildPath(repoRoot, "envs\kuro-llm310\pythonw.exe")
pythonExe = fso.BuildPath(repoRoot, "envs\kuro-llm310\python.exe")

sh.CurrentDirectory = repoRoot

If fso.FileExists(pythonwExe) Then
    shellApp.ShellExecute pythonwExe, """" & launcherScript & """", repoRoot, "open", 1
ElseIf fso.FileExists(pythonExe) Then
    cmd = """" & pythonExe & """ """ & launcherScript & """"
    sh.Run cmd, 0, False
Else
    cmd = "py """ & launcherScript & """"
    sh.Run cmd, 0, False
End If
