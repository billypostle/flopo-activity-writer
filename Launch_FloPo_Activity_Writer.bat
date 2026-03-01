@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Launches FloPo Activity Writer, starts server if needed, then opens browser.

cd /d "%~dp0"
set "APP_URL=http://127.0.0.1:8000"

set "PYTHON_EXE=C:\Users\billy\AppData\Local\Programs\Python\Python312\python.exe"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=%cd%\.venv\Scripts\python.exe"
)

if not exist "%PYTHON_EXE%" (
  echo Python executable not found at:
  echo %PYTHON_EXE%
  echo.
  echo Install Python or update PYTHON_EXE in this launcher.
  pause
  exit /b 1
)

set "LISTENING=0"
for /f "delims=" %%L in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do set "LISTENING=1"

if /I not "%LISTENING%"=="1" (
  echo Starting FloPo Activity Writer server...
  powershell -NoProfile -Command "Start-Process -WindowStyle Minimized -FilePath '%PYTHON_EXE%' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory '%cd%'"

  set "READY=0"
  for /L %%I in (1,1,30) do (
    ping -n 2 127.0.0.1 >nul
    set "LISTENING=0"
    for /f "delims=" %%L in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do set "LISTENING=1"
    if /I "!LISTENING!"=="1" (
      set "READY=1"
      goto :opened
    )
  )
)

:opened
start "" "%APP_URL%"
exit /b 0
