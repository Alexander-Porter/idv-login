### QQ群[https://www.bilibili.com/opus/920131433914171416]
### 视频教程（与文字版冲突时以文字版为准）[https://www.bilibili.com/video/BV1qM4m1Q7i8]

## idv-login-netease(绕过注册时间限制-一键法)

Github地址：[https://github.com/Alexander-Porter/idv-login/tree/main](https://github.com/Alexander-Porter/idv-login/tree/main)
* 自己构建
    * 在 Python 官网下载 Python [Python.org](https://www.python.org/downloads/release/python-3123/)
    * 例：64 位电脑 [Windows installer (64-bit)](https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe)
    * 安装Python时要自定义(Custom)安装，**添加到Path**和**为所有用户安装**和**pip**。
    * Windows7 下未经测试
    * 下载[代码](https://github.com/Alexander-Porter/idv-login/archive/refs/heads/server.zip)到本地，解压
    * 进入解压后的目录，shift+鼠标右键，选择打开Powershell或终端
    * 输入以下代码并回车
```bash
python serverSetup.py
```

* 登录方法
    * 鼠标双击运行run.bat (注意:部分杀软可能会因为修改hosts文件报毒，放行即可)
    * 保持终端窗口打开，同时打开第五人格

* 不想丸啦
    * 鼠标双击运行恢复hosts.bat

## idv-login-netease(绕过注册时间限制-Proxifier法)

* 自己构建
    * 切换分支到proxifier
    * 在 Python 官网下载 Python [Python Release Python 3.11.4 | Python.org](https://www.python.org/downloads/release/python-3114/)
    * 例：64 位电脑 [Windows installer (64-bit)](https://www.python.org/ftp/python/3.11.4/python-3.11.4-amd64.exe)
    * 安装Python时要选择**添加到Path**和**为所有用户安装**
    * 下载[代码](https://github.com/Alexander-Porter/idv-login/archive/refs/heads/main.zip)到本地，解压
    * 进入解压后的目录，shift+鼠标右键呼出 Powershell
```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
pip install mitmproxy
```
* 安装证书
    * 在Powershell中输入`mitmweb -s netease.py`回车，等待出现浏览器窗口
    * 打开文件管理器，输入`%userprofile%/.mitmproxy`回车
    * 点击`mitmproxy-ca`文件，安装位置选本地机器，一路下一步，直到选择证书存储位置，选自己选择，选**受信任的根证书颁发者**，完成安装。
* 配置Proxifier
    * 下载Proxifier 4
    * 双击下载下来的`netease.ppx`，确定导入配置
    * 至此，准备阶段结束
* 登录方法
    * 进入解压后的目录，shift+鼠标右键呼出 Powershell
    * 在Powershell中输入`mitmweb -s netease.py`回车，等待出现浏览器窗口
    * 打开Proxifier
    * 登录游戏并**进入庄园后**关闭Proxifier[可选]


 

