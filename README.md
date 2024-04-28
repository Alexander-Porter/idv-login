### QQ群[https://www.bilibili.com/opus/920131433914171416]
### 视频教程（与文字版冲突时以文字版为准）[https://www.bilibili.com/video/BV1qM4m1Q7i8]

## idv-login-netease(绕过注册时间限制-一键法)

Github地址：[https://github.com/Alexander-Porter/idv-login/tree/main](https://github.com/Alexander-Porter/idv-login)

* 使用预打包版
    * **重要！**关于安全性：仓库中的成品exe为*自动化*打包，不存在被注入恶意盗号代码的可能性。然而，对于网络上的转载链接，请自行确认其SHA256校验值与release->checksum中的SHA256是否相同，否则有被盗号风险。[在线计算SHA256](https://www.metools.info/code/c92.html)。如果希望自己构建，请参看下一节。
* 自己构建（可选）
    * 在 Python 官网下载 Python [Python.org](https://www.python.org/downloads/release/python-3123/)
    * 例：64 位电脑 [Windows installer (64-bit)](https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe)
    * 安装Python时要**使用管理员权限**，自定义(Custom)安装，**添加到Path**、**为所有用户安装**和**pip**。
    * Windows7 下未经测试
    * 下载[代码](https://github.com/Alexander-Porter/idv-login/archive/refs/heads/one-key.zip)到本地，解压
    * 进入解压后的目录，shift+鼠标右键，选择打开Powershell或终端
    * 输入以下代码并回车
```bash
pip install -r requirements.txt
pyinstaller -F one-key.py
```
    * dist文件夹中的one-key.exe就是成品


* 登录方法
    * 鼠标双击运行one-key.exe (注意:部分杀软可能会因为修改hosts文件报毒，放行即可)
    * 保持终端窗口**打开**，然后打开第五人格

* 不想丸啦
    * 在文件资源管理器里输入`%windir%\System32\drivers\etc`并回车，删除`hosts`文件，将bak文件重命名为`hosts`
