@echo off
setlocal
cd /d "%~dp0"
python-embed\python.exe "%~dp0src\\main.pyc" %*
endlocal
