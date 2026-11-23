@echo off
rem Encerra o vigia (e o navegador que ele abriu).
chcp 65001 >nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.Name -ne 'powershell.exe' } | Where-Object { ($_.Name -like 'python*.exe' -and $_.CommandLine -like '*-m vigia*') -or ($_.CommandLine -like '*%~dp0dados\navegador*') } | ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null }"
if not "%1"=="silencioso" (echo Vigia parado. & pause)
