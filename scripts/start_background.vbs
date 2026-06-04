Set objShell = CreateObject("Wscript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strScriptsDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
strProjectRoot = objFSO.GetParentFolderName(strScriptsDir)

objShell.CurrentDirectory = strProjectRoot

If objFSO.FileExists(objFSO.BuildPath(strProjectRoot, ".venv\Scripts\python.exe")) Then
    strPython = objFSO.BuildPath(strProjectRoot, ".venv\Scripts\python.exe")
ElseIf objFSO.FileExists(objFSO.BuildPath(strProjectRoot, "venv\Scripts\python.exe")) Then
    strPython = objFSO.BuildPath(strProjectRoot, "venv\Scripts\python.exe")
Else
    strPython = "python"
End If

objShell.Run "cmd /c """ & strPython & """ -m spy_bot", 0, False
