jadx_path = r"jadx/bin/jadx"
import base64
import json
import os,subprocess,re
import base64
import logging

import requests

def validate(data, key):
    s_key = data["UNISDK_SERVER_KEY"]
    try:
        val=data[key]
        if key=='UNISDK_SERVER_KEY' or key=='APP_CHANNEL':
            return val
        decode = base64.b64decode(s_key)
        if len(decode) != 124:
            logging.error(f"f size error: {len(decode)}<>124")
            return val

        copy_of_range = decode[:62]
        copy_of_range2 = decode[62:124]
        hash_map = {}

        for i in range(62):
            hash_map[(copy_of_range[i] - 76) + copy_of_range2[i]] = copy_of_range2[i]

        char_array = list(val)
        for i in range(len(char_array)):
            b = ord(char_array[i])
            if b in hash_map:
                char_array[i] = chr(hash_map[b])

        return ''.join(char_array)
    except Exception as e:
        logging.exception("Exception occurred")
        return str
github_token=os.getenv("GITHUB_TOKEN")
def updateCloudRes(item):
    #get now cloud res
    url="https://api.github.com/repos/KKeygen/idv-login/contents/assets/cloudRes.json"
    headers={"Authorization":"token "+github_token}
    r=requests.get(url,headers=headers)
    fileInfo=r.json()
    sha=fileInfo["sha"]
    import base64
    import json
    content=base64.b64decode(fileInfo["content"]).decode()
    data=json.loads(content)
    #update cloud res


    import time
    data["lastModified"]=int(time.time())
    data["data"].append(item)

    commitMessage=f"Live update for {item['game_id']}-{item['app_channel']}"
    dataStr=json.dumps(data,indent=4)
    dataStr=base64.b64encode(dataStr.encode()).decode()
    data={
        "message":commitMessage,
        "content":dataStr,
        "sha":sha
    }
    r=requests.put(url,headers=headers,json=data)
    print(r.json())

def getNeteaseGameInfo(apkPath):
    app_channel = None
    application=None
    package_name = None
    log_key=None
    game_id=None

    os.makedirs('res', exist_ok=True)
    subprocess.check_call([jadx_path, apkPath, '--no-src', '-dr', 'res'])


    import xml.etree.ElementTree as ET

    with open('res/AndroidManifest.xml', 'r') as f:
        data = f.read()
        root = ET.fromstring(data)
        package_name = root.attrib['package']
        application = root.find('application')
        if "huawei" in package_name or "HUAWEI" in package_name:
            app_channel = "huawei"
        elif "xiaomi" in package_name or "XIAOMI" in package_name or "mi" in package_name or "MI" in package_name:
            app_channel = "xiaomi_app"
        elif "com.tencent" in package_name:
            app_channel = "myapp"
        elif "honor" in package_name or "hihonor" in package_name:
            app_channel = "honor_sdk"
        elif "aligames" in package_name:
            app_channel = "uc_platform"

    #get channel data
    with open(f'res/assets/{app_channel}_data', 'r') as f:
        myData = f.read()
        myData = base64.b64decode(myData).decode()
        myData = json.loads(myData)
        log_key=validate(myData, "JF_LOG_KEY")
        app_channel=validate(myData, "APP_CHANNEL")
        game_id=validate(myData, "JF_GAMEID")

    if app_channel=='xiaomi_app':
        namespaces = {'android': 'http://schemas.android.com/apk/res/android'}
        meta_data = application.find("./meta-data[@android:name='miGameAppId']", namespaces)
        miGameAppId = meta_data.attrib['{http://schemas.android.com/apk/res/android}value']
        channelData=miGameAppId
    if app_channel=='huawei':
        with open('res/assets/agconnect-services.json', 'r') as f:
            hw_data=json.loads(f.read())
            channelData=hw_data['client']
    if app_channel=='myapp':
        #open ysdkconf.ini
        with open('res/assets/ysdkconf.ini', 'r') as f:
            channelData={
                "wx_appid":"",
                "channel":""
            }
            data = f.read()
            data = data.split('\n')
            for line in data:
                line = line.strip()
                try:
                    if 'WX_APP_ID' in line:
                        channelData['wx_appid'] = line.split('=')[1]
                    elif 'OFFER_ID' in line:
                        channelData['channel'] = line.split('=')[1]
                    elif 'QQ_APP_ID' in line:
                        channelData['channel'] = line.split('=')[1]
                except:
                    pass
    if app_channel=='honor_sdk':
        channelData = {}
        namespaces = {'android': 'http://schemas.android.com/apk/res/android'}
        app_id_meta = application.find("./meta-data[@android:name='com.hihonor.iap.sdk.appid']", namespaces)
        cp_id_meta = application.find("./meta-data[@android:name='com.hihonor.iap.sdk.cpid']", namespaces)
        if app_id_meta is not None:
            channelData['app_id'] = app_id_meta.attrib['{http://schemas.android.com/apk/res/android}value']
        if cp_id_meta is not None:
            channelData['cp_id'] = cp_id_meta.attrib['{http://schemas.android.com/apk/res/android}value']
        # Extract sdk_ver from ReadMe_UniSDK.txt
        readme_path = 'res/ReadMe_UniSDK.txt'
        if os.path.exists(readme_path):
            with open(readme_path, 'r') as f:
                for line in f:
                    m = re.match(r'honor_sdk_\d+\s+([\d.]+)', line.strip())
                    if m:
                        channelData['sdk_ver'] = m.group(1)
                        break
    if app_channel=='uc_platform':
        channelData = {}
        channelData['app_id'] = validate(myData, "APPID")
        channelData['uc_game_id'] = int(channelData['app_id']) if channelData['app_id'].isdigit() else channelData['app_id']
        channelData['package_name'] = package_name
        # 从 AndroidManifest 提取 versionCode 和 versionName
        namespaces = {'android': 'http://schemas.android.com/apk/res/android'}
        vc = root.attrib.get('{http://schemas.android.com/apk/res/android}versionCode', '')
        vn = root.attrib.get('{http://schemas.android.com/apk/res/android}versionName', '')
        if vc:
            channelData['version_code'] = int(vc)
        if vn:
            channelData['version_name'] = vn
        channel_infos_path = 'res/assets/channel_infos_data'
        if os.path.exists(channel_infos_path):
            with open(channel_infos_path, 'r') as f:
                ci_data = json.loads(f.read())
                if 'version' in ci_data:
                    channelData['sdk_ver'] = ci_data['version'].lstrip('V')
        sdk_info_path = 'res/assets/ucgamesdk/config/sdk_info.txt'
        if 'sdk_ver' not in channelData and os.path.exists(sdk_info_path):
            with open(sdk_info_path, 'r') as f:
                for line in f:
                    m = re.match(r'version=([\d.]+)', line.strip())
                    if m:
                        channelData['sdk_ver'] = m.group(1)
                        break

    RES={}
    RES["package_name"]=package_name
    RES["app_channel"]=app_channel
    RES["log_key"]=log_key
    RES["game_id"]=game_id
    RES[app_channel]=channelData
    print(RES)
    print(json.dumps(RES))
    if app_channel in ["xiaomi_app","huawei","myapp","honor_sdk","uc_platform"]:
        updateCloudRes(RES)
getNeteaseGameInfo("app.apk")