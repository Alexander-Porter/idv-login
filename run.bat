@echo off
%1 mshta vbscript:CreateObject("Shell.Application").ShellExecute("cmd.exe","/c %~s0 ::","","runas",1)(window.close)&&exit
cd /d "%~dp0"
cd /d %~dp0
echo "��¼�ɹ����ҽ�����Ϸ���ٹرձ�����"
mitmweb -s netease.py --mode transparent --allow-hosts service.mkey.163.com --set block_global=false
pause