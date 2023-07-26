# idv-login
* 准备 Python 环境
    * 在 Python 官网下载 Python [Python Release Python 3.11.4 | Python.org](https://www.python.org/downloads/release/python-3114/)
    * 例：64 位电脑 [Windows installer (64-bit)](https://www.python.org/ftp/python/3.11.4/python-3.11.4-amd64.exe)
    * 安装时带"pip"和"path"的选项要打勾
    * Windows7 只能用老版本，百度自搜
* 安装依赖
    * 下载代码到本地，解压
    * 进入解压后的目录，shift+鼠标右键呼出 powershell
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
    * 在 dist 文件夹得到成品
