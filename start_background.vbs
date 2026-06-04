Set objShell = CreateObject("Wscript.Shell")
strPath = Wscript.ScriptFullName
Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objFile = objFSO.GetFile(strPath)
strFolder = objFSO.GetParentFolderName(objFile)

objShell.CurrentDirectory = strFolder
objShell.Run "cmd /c .\.venv\Scripts\python.exe bot.py", 0, False
