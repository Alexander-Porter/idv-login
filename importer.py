import easygui as g
from urllib.parse import urlparse, parse_qsl
import json
import os
model={
    "type":0,
    "name":"AccountName",
    "params":{}
}
filename = 'accounts.json'
if os.path.exists(filename):
    with open(filename, 'r') as f:
        accounts = json.load(f)
else:
    accounts=[]
    from pathlib import Path
    Path("accounts.json").touch()
def create_netease(name,suffix,data):
    # 根据suffix创建账号备注
    account_name = name+ suffix
    netease = model.copy()
    netease["name"] = account_name
    netease["params"] = data.copy()
    accounts.append(netease)
def parse_scan(scan_data):
    
    url = scan_data
    parsed = urlparse(url)
    params = parse_qsl(parsed.query)
    params = dict(params)
    print(params)
    return (params)
def parse_confirm(scan_data):
    params = parse_qsl(scan_data)
    params = dict(params)
    print(params)
    return (params)
def import_netease():
    scan_data=parse_scan(g.enterbox("/scan"))
    token_data=parse_confirm(g.enterbox("/confirm_login"))
    scan_data.update(token_data)
    account_name=g.enterbox('账号备注') 
    #官服特殊逻辑-Begin
    if "a" in scan_data["cv"]:
        create_netease(account_name,"-And",scan_data)
        scan_data["cv"] = scan_data["cv"].replace("a", "i")
        create_netease(account_name,"-IOS",scan_data)
    else:
        create_netease(account_name,"-IOS",scan_data)
        scan_data["cv"] = scan_data["cv"].replace("i", "a")
        create_netease(account_name,"-And",scan_data)

    with open(filename, 'w') as f:
         f.write(json.dumps(accounts,indent=4))
    #官服特殊逻辑-End

    return ""
def import_third_party():
    scan_data=parse_scan(g.enterbox("/scan"))
    token_data=parse_confirm(g.enterbox("/confirm_login"))
    scan_data.update(token_data)
    account_name=g.enterbox('账号备注') 
    third_party = model.copy()
    third_party["name"] = account_name
    third_party["params"] = scan_data
    third_party["type"]=1
    accounts.append(third_party)
    return ""

msg = "选择账号类型"
title = "账号导入"
choicess_list = ["官服(IOS/Android)","渠道服"]
reply = g.indexbox(msg,choices=choicess_list)
print(reply)
match reply:
    case 0:
        import_netease()
    case 1:
        import_third_party()
with open(filename, 'w') as f:
    f.write(json.dumps(accounts,indent=4))