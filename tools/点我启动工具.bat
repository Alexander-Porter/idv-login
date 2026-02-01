@echo off
setlocal
cd /d "%~dp0"
python-embed\python.exe -m src.main %*
endlocal
