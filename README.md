# IdentityV-login-helper(绕过注册时间限制-一键法)

### 项目仓库：[click](https://github.com/Alexander-Porter/idv-login)
### QQ群：[click](https://www.bilibili.com/opus/920131433914171416)
### 视频教程（已过时）：[click](https://www.bilibili.com/video/BV1qM4m1Q7i8)

* 使用预打包版
    * **重要**！关于安全性：仓库中的成品exe为*自动化*打包，不存在被注入恶意盗号代码的可能性。然而，对于网络上的转载链接，请自行确认其`sha256`校验值与release->checksum中的`sha256`是否相同，否则有被盗号风险。你可以在`powershell`中输入以下命令来计算文件的`sha256`值。
    ```bash
    Get-FileHash <FileName>
    ```
    例如，计算v10.0.0.1-beta版本的`sha256`可以使用以下命令：
    ```bash
    PS D:\> Get-FileHash idv-login-v10beta-v10.0.0.1-beta.exe

    Algorithm       Hash
    ---------       ----
    SHA256          3F413E02C44772A99BC06153F21DF7E4A904C0C82457FC988890994DB88368BF
    ```
    如果希望自己构建，请参看下一节。
    * 下载方式：在页面右侧的auto-release处下载
* 自己构建（可选）
    * 在 Python 官网下载 Python [Python.org](https://www.python.org/downloads/release/python-3123/)
    * 例：64 位电脑 [Windows installer (64-bit)](https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe)
    * 安装Python时要**使用管理员权限**，自定义(Custom)安装，**添加到Path**、**为所有用户安装**和**pip**。
    * 由于新版本的Python **不支持** Windows7，如需在Windows7上构建本程序，可能需要借助**Anaconda**之类的软件安装支持Windows7的python（如 python 3.8）进行构建，具体教程请自行百度。
    * 下载[代码](https://github.com/Alexander-Porter/idv-login/archive/refs/heads/one-key.zip)到本地，解压
    * 进入解压后的目录，shift+鼠标右键，选择打开Powershell或终端
    * 输入以下代码并回车
    ```bash
    pip install -r requirements.txt
    pyinstaller -F src/main.py -n idv-login-v10beta.exe -i assets/icon.ico --version-file assets/version.txt --uac-admin
    ```
    * dist文件夹中的idv-login-v10beta.exe就是成品


* 登录方法
    * 鼠标双击运行idv-login-v10beta.exe (注意:部分杀软可能会因为修改hosts文件报毒，放行即可)
    * 保持终端窗口**打开**，然后打开第五人格

* 不想丸啦
    * 在文件资源管理器里输入`%windir%\System32\drivers\etc`并回车，删除`hosts`文件，即可解除工具对网易登录的劫持。