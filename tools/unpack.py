jadx_path = r"jadx/bin/jadx"
import base64
import json
import os,subprocess,re
def getNeteaseGameInfo(apkPath):
    app_channel = None
    application=None
    package_name = None
    log_key=None
    game_id=None
    #jadx apkPath --single-class com.netease.dwrg.Channel   --output-format json
    #use jadx to get package name
    os.makedirs('res', exist_ok=True)
    subprocess.check_call([jadx_path, apkPath, '--no-src', '-dr', 'res'])
    #reading res/assets/channel_auth_data, which is a base64 encoded json file
    with open('res/assets/ntunisdk_common_data', 'r') as f:
        data = f.read()
        #decode base64
        data = base64.b64decode(data).decode()
        #load json
        data = json.loads(data)
        app_channel = data.get('APP_CHANNEL')
        game_id = data.get('COMMON_JF_GAMEID')
        
    #reading AndroidManifest.xml
    import xml.etree.ElementTree as ET

    with open('res/AndroidManifest.xml', 'r') as f:
        data = f.read()
        root = ET.fromstring(data)
        package_name = root.attrib['package']
        application = root.find('application')
        #use regular expression to get package name com.netease.???.xxxx -> com.netease.???
        package_name=re.search(r'(com\.netease.+?)\.\w+',package_name).group(1)


    if app_channel=='xiaomi_app':
        namespaces = {'android': 'http://schemas.android.com/apk/res/android'}
        meta_data = application.find("./meta-data[@android:name='miGameAppId']", namespaces)
        miGameAppId = meta_data.attrib['{http://schemas.android.com/apk/res/android}value']
        channelData=miGameAppId
    if app_channel=='huawei':
        with open('res/assets/agconnect-services.json', 'r') as f:
            hw_data=json.loads(f.read())
            channelData=hw_data['client']
    RES={}
    RES["package_name"]=package_name
    RES["app_channel"]=app_channel
    RES["log_key"]=log_key
    RES["game_id"]=game_id
    RES[app_channel]=channelData
    print(RES)
    print(json.dumps(RES))
getNeteaseGameInfo("app.apk")