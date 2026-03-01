@echo off
setlocal

REM Stops uvicorn processes running app.main:app for FloPo Activity Writer.

powershell -NoProfile -Command ^
  "$targets = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn app.main:app*' }; " ^
  "if (-not $targets) { Write-Output 'No running FloPo Activity Writer server found.'; exit 0 }; " ^
  "$targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('Stopped PID ' + $_.ProcessId) }"

exit /b 0
