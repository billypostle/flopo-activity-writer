@echo off
setlocal
cd /d "%~dp0\Tools\Activity_Writer"
call Launch_FloPo_Activity_Writer.bat
exit /b %errorlevel%
