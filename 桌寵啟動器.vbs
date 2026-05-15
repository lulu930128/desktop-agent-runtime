Set sh = CreateObject("WScript.Shell")
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ""Set-Location 'C:\kuro'; py launcher.py""", 0, False

