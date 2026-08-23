Option Explicit

Dim sh, shellApp, fso
Dim repoRoot, launcherScript, workPanelEntry, pythonwExe, pythonExe
Dim launcherArgs, cmd

Set sh = CreateObject("WScript.Shell")
Set shellApp = CreateObject("Shell.Application")
Set fso = CreateObject("Scripting.FileSystemObject")

repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
launcherScript = fso.BuildPath(repoRoot, "launcher_qt.py")
workPanelEntry = fso.BuildPath(repoRoot, "pet-electron\renderer-dist\work-panel.html")
pythonwExe = fso.BuildPath(repoRoot, "envs\kuro-llm310\pythonw.exe")
pythonExe = fso.BuildPath(repoRoot, "envs\kuro-llm310\python.exe")
launcherArgs = """" & launcherScript & """ --work-panel"

sh.CurrentDirectory = repoRoot

If WScript.Arguments.Named.Exists("check") Then
    WScript.Quit 0
End If

If Not fso.FileExists(launcherScript) Then
    Call MsgBox("Kuro launcher was not found: " & launcherScript, vbCritical, "Kuro Work Panel")
    WScript.Quit 2
End If

If Not fso.FileExists(workPanelEntry) Then
    Call MsgBox( _
        "The new work panel build was not found: " & workPanelEntry & vbCrLf & _
        "Run npm run build:renderer in pet-electron first.", _
        vbCritical, _
        "Kuro Work Panel" _
    )
    WScript.Quit 2
End If

If fso.FileExists(pythonwExe) Then
    shellApp.ShellExecute pythonwExe, launcherArgs, repoRoot, "open", 1
ElseIf fso.FileExists(pythonExe) Then
    cmd = """" & pythonExe & """ " & launcherArgs
    sh.Run cmd, 0, False
Else
    Call MsgBox("Kuro Python was not found: " & pythonwExe, vbCritical, "Kuro Work Panel")
    WScript.Quit 2
End If
