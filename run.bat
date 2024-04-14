 cd /d %~dp0
 echo "登录成功，且进入游戏后再关闭本程序"
 mitmweb -s netease.py --mode transparent --allow-hosts service.mkey.163.com --set block_global=false
 pause