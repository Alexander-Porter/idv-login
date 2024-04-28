@echo off
%1 mshta vbscript:CreateObject("Shell.Application").ShellExecute("cmd.exe","/c %~s0 ::","","runas",1)(window.close)&&exit
#从etc的目录下的bak文件恢复
copy /y %windir%\System32\drivers\etc\hosts.bak %windir%\System32\drivers\etc\hosts