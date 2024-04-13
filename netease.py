import json
from mitmproxy import http, ctx
loginMethod=[  {
                "name": "手机账号",
                "icon_url": "",
                "text_color": "",
                "hot": True,
                "type": 7,
                "icon_url_large": ""
            },
            {
                "name": "快速游戏",
                "icon_url": "",
                "text_color": "",
                "hot": True,
                "type": 2,
                "icon_url_large": ""
            },
            {
                "login_url": "",
                "name": "网易邮箱",
                "icon_url": "",
                "text_color": "",
                "hot": True,
                "type": 1,
                "icon_url_large": ""
            }]
pcIndo={
            "extra_unisdk_data": "",
            "from_game_id": "h55",
            "src_app_channel": "netease",
            "src_client_ip": "",
            "src_client_type": 1,
            "src_jf_game_id": "h55",
            "src_pay_channel": "netease",
            "src_sdk_version": "3.15.0",
            "src_udid": ""
        }
def request(flow = None):
    if "mpay" in flow.request.url:
        ctx.log("Hit")
        flow.request.query["cv"]="i4.7.0"
        if(flow.request.method == "POST"):
            ctx.log("POST")
            ctx.log(flow.request.get_text())
            #text is key=value&key=value
            newBody = dict(x.split("=") for x in flow.request.get_text().split("&"))
            newBody["cv"]="i4.7.0"
            newBody.__delitem__("arch")
            flow.request.set_text("&".join([f"{k}={v}" for k,v in newBody.items()]))
        if 'devices' in flow.request.url:
            flow.request.query["app_mode"]=2
        return None


def response(flow = None):
    if 'login_methods' in flow.request.url:
        ctx.log('Hit!')
        newLoginMethods = json.loads(flow.response.get_text())
        newLoginMethods["entrance"].append(loginMethod)
        newLoginMethods["select_platform"]=True
        newLoginMethods["qrcode_select_platform"]=True
        for i in newLoginMethods["config"]:
            newLoginMethods["config"][i]["select_platforms"]=[0,1,2,3,4]
        flow.response.set_text(json.dumps(newLoginMethods))
        return None
    if 'pc_config' in flow.request.url:
        newPcConfig = json.loads(flow.response.get_text())
        newPcConfig["game"]["config"]["cv_review_status"] = 1
        flow.response.set_text(json.dumps(newPcConfig))
        return None
    if 'devices' in flow.request.url:
        ctx.log("dataHit")
        newDevices = json.loads(flow.response.get_text())
        newDevices["user"]["pc_ext_info"] = pcIndo
        flow.response.set_text(json.dumps(newDevices))
        return None
        

