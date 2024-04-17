@echo off  
title 第五人格账号密码登录
color 0A
setlocal enabledelayedexpansion  
 
for /f "delims=" %%a in (path.txt) do (  
    set "fullPath=%%a"
REM 读取path.txt内容到变量fullpath
)
for %%F in ("%fullPath%") do (  
    set "dirPath=%%~dpF"  
    cd /d "!dirPath!" 
REM 读取游戏目录
	start dwrg.exe
	echo 请在登入游戏后关闭本窗口
) 

endlocal
:: 后台静默启动mitmweb  
mitmweb -s netease.py --mode transparent --allow-hosts service.mkey.163.com --set block_global=false --no-web-open-browser -q
pause
