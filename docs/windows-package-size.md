# Windows 包的 Qt 裁剪

## 基线与边界

审计基线是 `main` 的 `5359586d53f449bf5836aa8753d472863dfd500c`。
只依据这一版本的实际代码和二进制依赖裁剪，不为尚未使用的 Qt 功能预留文件。
本改动独立于移除内嵌浏览器的迁移：当前 Qt Widgets、QtWebEngine、渠道登录行为不变。
macOS PyInstaller 构建不改。

Windows 实际链路不是 README 中的单文件 PyInstaller 示例，而是：

1. `pack.yaml`（手动构建）或 `build-stable.yaml`（版本发布）。
2. 下载 CPython 3.12.10 embed x64，pip 安装 requirements 和 pywin32，缓存完整解释器。
3. 编译应用 `src`，复制解释器、应用、mpay 资源及 bat 到 `dist`。
4. **仅裁剪 `dist/python-embed/Lib/site-packages/PyQt6` 副本**。
5. 用该副本的 Windows Python 做 Qt 冒烟验收，再由 Inno Setup 压缩 `dist`。

原流程在整个工作区递归改名/移动 pyc、删除 py，会同时修改依赖缓存和构建脚本。
现在用 `compileall -b src` 直接生成应用相邻 pyc，仅在 dist 中删除应用 py 和缓存目录。
第三方包保留标准源码布局，不再把其所有 pyc 跨目录搬动。完整依赖缓存不被瘦身步骤修改。缓存 key 升至 `deps-v2`，避免复用旧流程已经删掉源码的缓存。
`verification.yaml` 和 `generate_verification.py` 仍使用原 `src` 编译与规范化 marshal 校验，
应用代码、启动 bat、校验格式均未改变。

## 为什么这些文件保留/删除

`tools/slim_windows_qt.py` 先分析完整计划，再删除 staging 文件，并输出逐文件 JSON。

- 应用直接导入仅 `QtCore`、`QtGui`、`QtNetwork`、`QtWidgets`、`QtWebEngineCore`、`QtWebEngineWidgets`。
- 不能只按 Python import 删 DLL。读取各绑定的 SIP `%Import`，保留间接需要的
  `QtPrintSupport` 和 `QtWebChannel`；再递归读取所有保留 PE 的普通及延迟导入表。
- `Qt6Quick`、`Qt6QuickWidgets`、`Qt6Qml` 等 DLL 是 WebEngine 的真实硬依赖，保留。
  应用没有 QML engine/import、Qt Quick 界面，因此删除 QML 模块目录，不混淆 DLL 与 QML 组件。
- 显式保留实际动态加载入口：Windows 平台、默认 Windows 样式、ICO 图标、
  Windows Schannel TLS 和网络状态插件。页面图片由 Chromium 解码，不是 Qt imageformats 插件。
- 保留 `opengl32sw.dll` 与 `d3dcompiler_47.dll`，因为当前图形界面在无可用硬件驱动时会走软件渲染，
  这不是未来功能的预留。
- 保留 `QtWebEngineProcess.exe`、release Chromium 资源、ICU、release V8 快照。
  删除 debug 资源与 debug V8 快照。删除未使用的 DevTools 资源：Qt 6.11.2
  [源码](https://github.com/qt/qtwebengine/blob/v6.11.2/src/core/resource_bundle_qt.cpp)
  通过 `AddOptionalDataPackFromPath` 加载它，应用未开启 DevTools。
- 保留全部 Chromium locale pak。当前 Qt 从操作系统 `QLocale` 选择 locale；
  登录页的 `setHttpAcceptLanguage("zh-CN,...")` 不等于更改 Chromium 本地 UI locale。
  普通 Qt `.qm` 翻译删除，因为应用没有安装 `QTranslator`。
- 删除未用绑定、未引用 Qt DLL、Qt Multimedia 的 FFmpeg DLL、开发工具、SIP 描述、类型桩、
  API 补全文件和其他未用插件。wheel 的 dist-info（含许可证）不动。

依据：
[Qt WebEngine 部署文档](https://doc.qt.io/qt-6.11/qtwebengine-deploying.html)、
[Qt 6.11.2 资源与 locale 选择代码](https://github.com/qt/qtwebengine/blob/v6.11.2/src/core/web_engine_library_info.cpp)、
当前 Windows wheels 内 SIP 描述及 PE 导入表。

## 可复现测量

2026-10-21 在 Linux 上下载并解包官方 Windows wheels，**没有在 Linux 执行 Windows DLL**：

| Qt 目录净文件字节 | 裁剪前 | 裁剪后 | 减少 |
| --- | ---: | ---: | ---: |
| Windows PyQt6 payload | 575,463,820 | 347,801,065 | 227,662,755（39.56%） |
| MiB（2^20 bytes） | 548.81 | 331.69 | 217.12 |

这不是整个安装包体积，也不是 Inno Setup 压缩率。Qt 之外的依赖和资源不计入这个表。
原 Qt 中单个 `Qt6WebEngineCore.dll` 已有 194.02 MiB，当前确实使用内嵌浏览器，不能删除。
最大可删项为资源 88.23 MiB（含 debug 与可选 DevTools）、未用 bin 76.20 MiB、
未用插件 14.35 MiB、QML 树 13.95 MiB、未加载 `.qm` 10.23 MiB。

固定测量版本及 SHA-256：

| Wheel | SHA-256 |
| --- | --- |
| pyqt6-6.11.0-cp310-abi3-win_amd64.whl | bd11b459c54dca068e988a42cf838303334f0d441b9d16d92ae6719fcb5ac6ba |
| pyqt6_qt6-6.11.2-py3-none-win_amd64.whl | 4b424ed1babbef07133eb2a4174c56c848d518767bca8e759aca2c8c9c313636 |
| pyqt6_sip-13.13.0-cp312-cp312-win_amd64.whl | c6b67d301ef64e13d313c728020616315c952473abb27029b2e5857b44a7b3e6 |
| pyqt6_webengine-6.11.0-cp310-abi3-win_amd64.whl | 5596ea8f7fd94a6b443c47f3c12dac619bedf5fabb646d2b8b4de1d73ec531cb |
| pyqt6_webengine_qt6-6.11.2-py3-none-win_amd64.whl | af13f13e6620de6d904b268343d901caeb7a39b15ead92f5dde8cdd69dac179b |

```bash
python -m pip install pefile==2024.8.26
python -m pip download --dest wheels --only-binary=:all: --no-deps \
  --platform win_amd64 --python-version 312 \
  PyQt6==6.11.0 PyQt6-WebEngine==6.11.0 PyQt6-Qt6==6.11.2 \
  PyQt6-WebEngine-Qt6==6.11.2 PyQt6-sip==13.13.0
python -c "from pathlib import Path; from zipfile import ZipFile; [ZipFile(p).extractall('wheel-stage') for p in Path('wheels').glob('*.whl')]"
python tools/slim_windows_qt.py --qt-root wheel-stage/PyQt6 \
  --source-root src --report qt-size.json
# 对一份可丢弃的 staging 副本添加 --apply 才会实际裁剪。
```

直接依赖仍按原 requirements 锁定；其允许的 Qt patch 版本可能随缓存/构建日期变化。
因此每次构建都记录实际安装版本、每个删除文件大小、保留文件清单、PE 依赖边，
并上传 `windows-qt-size-report`，而不是把本次测量值冒充以后的固定体积。

## 验收范围

- 已在 Linux 完成：源代码语法编译、workflow YAML 解析、官方 Windows PE/SIP 闭包、
  dry-run 与实际裁剪一致性、所有保留文件字节不变。
- CI 中使用裁剪后的 Windows embed Python，导入全部保留绑定、解码项目 ICO、
  加载 Schannel、创建真实 QWebEngineView，以本地合成 HTML 执行 JavaScript；30 秒超时即失败。
  这是打包冒烟，不是新增单元测试，也不会运行有 hosts/代理/证书副作用的 `main.py`。
- 冒烟不等于所有渠道的真实账号登录已验收，也不覆盖每种 GPU/操作系统 locale。
  Windows CI 运行结果与最终 installer 字节数以 PR 的实际构建记录为准；未成功时不得标为通过。
