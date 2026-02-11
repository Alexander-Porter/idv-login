@echo off
setlocal
cd /d "%~dp0"
python-embed\python.exe src/main.pyc %*
endlocal
