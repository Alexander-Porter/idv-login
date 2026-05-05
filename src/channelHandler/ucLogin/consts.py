# coding=UTF-8
"""UC/九游 SDK 常量。"""

# RSA 公钥（从 APK assets/config/uc_key.txt 提取，格式 "version|base64_der_pubkey"）
# 注意：此为启动密钥，运行时由 getSecurityKey 返回新密钥（通常 version=5）替换。
UC_RSA_PUBKEY_VERSION = 1
UC_RSA_PUBKEY_B64 = (
    "MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAKjnX9Dkb4gVT2PbXg9QLPUS"
    "moOQndKra4wfGwub16R/zjdqLJgDo6DisetD4diIw/1gjdSU+6nCEaiK"
    "+5a9F/8CAwEAAQ=="
)

# SDK API 端点 — 不同服务路由到不同 host
# URL 格式 http://{host}/ng/client/{service}?ver=0&df=adat&os=android
# 注意：必须使用 HTTP，HTTPS 连接会被 reset
UC_HOST_MAP = {
    # sdk.9game.cn: 初始化、认证、旧版登录
    "system.getSecurityKey": "sdk.9game.cn",
    "system.brand.check": "sdk.9game.cn",
    "system.config.check": "sdk.9game.cn",
    "si.apply": "sdk.9game.cn",
    "sngaccount.getIPSupportCountryCode": "sdk.9game.cn",
    "ucid.user.login": "sdk.9game.cn",
    "ucid.user.smsCodeLogin": "sdk.9game.cn",
    "ucid.user.ticketLogin": "sdk.9game.cn",
    "ucid.user.refreshLogin": "sdk.9game.cn",
    "auth.captcha.sendSmsCode": "sdk.9game.cn",
    "auth.captcha.getCommonCaptcha": "sdk.9game.cn",
    "guest.login": "sdk.9game.cn",
    # sdk-account.9game.cn: 统一账号（新版 SMS 登录）
    "unifiedAccount.sendSmsCode": "sdk-account.9game.cn",
    "unifiedAccount.loginBySmsCode": "sdk-account.9game.cn",
    "unifiedAccount.loginByServiceTicket": "sdk-account.9game.cn",
    "unifiedAccount.getUserSimpleInfo": "sdk-account.9game.cn",
    "unifiedAccount.generateAccountRemark": "sdk-account.9game.cn",
    "unifiedAccount.addGameAccount": "sdk-account.9game.cn",
    # sdknc.9game.cn: 配置、VIP
    "collect.realNameStrategy.get": "sdknc.9game.cn",
    "ucid.vip.getYyUserLevel": "sdknc.9game.cn",
    # sdklog.9game.cn: 日志
    "log.collect.sdklog": "sdklog.9game.cn",
    # sdkyymsg.9game.cn: 事件上报
    "client.event.report": "sdkyymsg.9game.cn",
    "column.base.getShowFramework": "sdkyymsg.9game.cn",
}
UC_DEFAULT_HOST = "sdk.9game.cn"

# ============ SDK 服务名常量 ============
# 初始化
SVC_GET_SECURITY_KEY = "system.getSecurityKey"
SVC_SI_APPLY = "si.apply"
# 新版统一账号登录（SDK 9.8.x）
SVC_SEND_SMS_CODE = "unifiedAccount.sendSmsCode"
SVC_SMS_LOGIN = "unifiedAccount.loginBySmsCode"
# 会话管理
SVC_REFRESH_LOGIN = "ucid.user.refreshLogin"

# ============ SDK 版本 ============
UC_SDK_VERSION = "9.8.1.4"

# ============ 游戏数据（默认值，实际从 cloudRes 读取）============
UC_APP_ID = "17"  # client.appId — SDK 硬编码 (ClientData.java)，所有游戏相同

# UC gameId（game 字段）— 每个游戏不同，从 APK uc_platform_data.APPID 解混淆获得
UC_GAME_ID = 800051  # h55 默认值

# h55 APK 信息 (com.netease.dwrg.aligames) — 默认值
UC_H55_VERSION_CODE = 260071256
UC_H55_VERSION_NAME = "2026.0107.1256"
