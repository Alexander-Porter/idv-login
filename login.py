from easygui import *
import json
import os
import pyautogui,requests
import time
import pyzbar.pyzbar as pyzbar
from PIL import Image


URL1 = "https://service.mkey.163.com/mpay/api/qrcode/scan"
URL2 = "https://service.mkey.163.com/mpay/api/qrcode/confirm_login"













#filename = 'path.txt'
#if os.path.exists(filename):
#    with open(filename, 'r') as f:
#        game_path = f.read()
#else:
#    from pathlib import Path
#    game_path=enterbox("输入游戏本体路径，不能有引号和空格。例如C:/dwrg/dwrg.exe")
#    with open(filename, 'w') as f:
#        f.write(game_path)


with open("accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)
names = [account["name"] for account in accounts]
msg = "请选择一个账号"
account_index = indexbox(msg, choices=names)
selected_account=accounts[account_index]
#p = subprocess.Popen(game_path, shell=True)






while True:
    try:
        screenshot = pyautogui.screenshot()
    except:
        pass
    screenshot.save('screenshot.png')
    with open('screenshot.png', 'rb') as image_file:
        image = Image.open(image_file)
        codes = pyzbar.decode(image)
        if codes:
            a=(codes[0].data.decode('utf-8'))
            if ("uuid" in a):
                break
    time.sleep(1)
uuid=a.replace("https://service.mkey.163.com/mpay/api/qrcode/scan?uuid=","")
selected_account['params']["uuid"]=uuid
params=selected_account['params']


response = requests.get(URL1, params=params)
r=response = requests.post(URL2, params=params)
print(r.json())
