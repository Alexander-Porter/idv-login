# idv-login
* 准备 Python 环境
    * 在 Python 官网下载 Python [Python Release Python 3.11.4 | Python.org](https://www.python.org/downloads/release/python-3114/)
    * 例：64 位电脑 [Windows installer (64-bit)](https://www.python.org/ftp/python/3.11.4/python-3.11.4-amd64.exe)
    * 安装时带"pip"和"path"的选项要打勾
    * Windows7 只能用老版本，百度自搜
* 安装依赖
    * 下载代码到本地，解压
    * 进入解压后的目录，shift+鼠标右键呼出 Powershell
```plain
pip install -r requirements.txt
```
    * 注意：这一步对网络环境要求较高（你懂的），如果实在很慢，百度搜索 *pip 换源*
* 构建
    * 在 powershell 窗口中输入以下两行命令
```plain
pyinstaller -F login.py --collect-all pyzbar
pyinstaller -F importer.py
```
    * 在 dist 文件夹得到成品login.exe importer.exe
* 账号导入方法
    * 所需：安卓设备一台，PC客户端
    * 手机打开第五人格确保客户端是最新的，并且账号已登录
    * 下载[Fiddler](https://telerik-fiddler.s3.amazonaws.com/fiddler/FiddlerSetup.exe)
    * 根据这篇[教程](https://blog.csdn.net/michaelwoshi/article/details/114173158) 配置好手机上Fiddler的抓包环境
       * PS.高版本安卓用户需要手动安装证书。在设置中搜索“证书”，选择从存储设备安装→CA证书，找到下载好的证书并安装
    *  用流量打开第五人格，点开扫码界面。此时切换为wifi，并且配置好代理。
    *  扫码并登录PC端一次
       * PS.如果扫码登录时提示网络错误之类，代表你这个渠道（例：华为）本工具不支持。背后的原因是部分渠道使用了证书固定。
    *  如果成功登录了，打开importer.exe。
    *  在Fiddler中找 ```Ctrl+F``` 到包含 ```mpay/api/qrcode/scan``` 的网络请求，选中，在Inspector→Raw选项卡中复制请求的Url（蓝色高亮），填入第一个对话框中
    *  再找到 ```mpay/api/qrcode/confirm_login``` 在Inspector→Textview选项卡中复制全部内容，填入第二个对话框中
    *  给你的账号起个备注，导入完成
* 登录方法
    * 打开login.exe和PC客户端，确保登录二维码完整出现在屏幕内，选择账号登录
       * PS.如果显示扫码成功但没有下一步反应，说明你的登录凭据过期。过期时间因渠道而异
