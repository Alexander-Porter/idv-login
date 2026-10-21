# 不再内嵌 WebView：范围、选型与迁移说明

## 范围和完成标准

本次以 `idv-login` main `5359586d53f449bf5836aa8753d472863dfd500c` 与
`idv-login-webui` fever `7ec786e5830b579a88ad22af40c26922d96add21` 的实际调用为边界。
不是将首页交给 `webbrowser.open()` 就算完成，也不按框架所有可能功能保留依赖。
游戏本身的内置页面不是本工具嵌入的窗口，原有 mitmproxy `/_idv-login/*` 服务继续兼容它。

需要迁移的实际工作有两类：

1. 启动器 Vue UI、原生操作桥和宿主窗口生命周期。
2. 登录浏览器的主世界注入、弹窗、回调协议、一次性响应正文、cookies，以及 MPay SDK 自己打开的网页。

保留 Qt Core/Gui/Widgets/Network，是因为原生选择器、UC 短信界面、华为账号填充、提示/更新对话框、跨线程调用和 MPay HWND 仍有实际调用；不是保守保留 WebEngine。

## 选择：普通 Firefox + 标准 WebDriver BiDi

使用已安装的 Firefox 153 ESR 或 158 正式版。启动前用不打开 profile 的 `--version` 检查；未来主版本须先审计其恢复文件格式/回退集合并更新支持，不能先打开旧登录资料再验证。Python 通过既有 `aiohttp` 连接该浏览器内置的 WebDriver BiDi，界面在独立进程的正常浏览器窗口中显示。
不捆绑 Firefox，不依赖 Playwright、Node、geckodriver、浏览器扩展或定制浏览器。

### 候选比较

| 候选 | 可复用的部分 | 当前能力的缺口 / 代价 | 结论 |
| --- | --- | --- | --- |
| 默认浏览器 + localhost 页面 | Vue、普通 HTTP API | 无法读取供应商 HttpOnly cookies、在页面创建前注入原生桥，或接管固定 `auth://` / `honorid://` 回调 | 不完整 |
| Tauri / Wails / Electron / 系统 WebView | 大多数现有网页 | 仍然内嵌 WebView，只换引擎/封装，不符合目标 | 不选 |
| 全部改为 Qt 原生 UI + HTTP 请求 | 原生选择器、部分扫码/短信 API | 仍需供应商动态验证码、第三方 OAuth、OPPO JS bridge、Bili 网页备用方式；不能用删除这些入口代替迁移 | 当前不是完整可行的最小方案 |
| Chromium CDP / Playwright + 专用 profile | DOM、cookies、预注入 | 自定义外部协议不保证经过 Fetch interception。Navigation API 可以拦主窗口，但父页面设置 `iframe.src` 等路径不能靠子页面脚本保证拦住。抢时序 stopLoading 不是安全保证 | 不选为唯一实现 |
| Chromium 扩展 / OS 协议处理器 | 某些回调可重定向 | 普通 webRequest 覆盖范围不等于任意自定义协议；注册全局 `auth`/`honorid` 会影响其他软件。需要扩展安装/发行和持续权限，仍要解决页面/框架生命周期 | 不为单个回调扩大系统影响 |
| Playwright Firefox | 页面控制成熟 | 其 Firefox 使用补丁构建，引入额外浏览器/驱动维护，不优于普通 Firefox 自带 BiDi | 不选 |
| 普通 Firefox BiDi | 主世界注入、DOM、cookies、网络响应、popup、专用 profile | 用户需要安装现代 Firefox；供应商对 Gecko 的真实兼容性仍须验收 | 本次选择 |

关键不是 Chromium 能否显示页面，而是能否在任何回调路径都不将令牌发给系统协议处理器。Firefox 在外部协议派发前检查专用 profile 中的 `network.protocol-handler.external.<scheme>`；为每个实际回调 scheme 显式设为 false。`external-default=false` 只是补充，不能声称它覆盖浏览器已有的全部 scheme-specific 默认值。

导航监听负责取得回调，不负责安全阻止派发。覆盖主窗口、iframe、用户触发 popup、fragment 及 HTTP 302 的 `Location`。实证发现 302 不会再产生第二次 custom `navigationStarted`，因此必须同时观察原始网络响应。

依据：
- [Firefox Remote Agent 安全模型](https://firefox-source-docs.mozilla.org/remote/Security.html)
- [主世界 preload 与子 frame](https://developer.mozilla.org/en-US/docs/Web/WebDriver/Reference/BiDi/Modules/script/addPreloadScript)
- [Gecko 外部协议派发实现](https://github.com/mozilla-firefox/firefox/blob/main/uriloader/exthandler/nsExternalHelperAppService.cpp)
- [Firefox 原生会话 cookies](https://github.com/mozilla-firefox/firefox/blob/main/browser/components/sessionstore/SessionCookies.sys.mjs)
- [Firefox 原生恢复文件](https://github.com/mozilla-firefox/firefox/blob/main/browser/components/sessionstore/SessionFile.sys.mjs)
- [Firefox profile 锁](https://github.com/mozilla-firefox/firefox/blob/main/toolkit/profile/nsProfileLock.cpp)
- [已验证 ESR 153.5.1 的 Windows launcher](https://hg.mozilla.org/releases/mozilla-esr153/raw-file/46f5f658a8fe6751cb4ef704999da57fb1bf1ea2/browser/app/winlauncher/LauncherProcessWin.cpp)
- [同版本 Windows stdout/console 处理](https://hg.mozilla.org/releases/mozilla-esr153/raw-file/46f5f658a8fe6751cb4ef704999da57fb1bf1ea2/widget/windows/WindowsConsole.cpp)
- [Chromium 非网络导航实现](https://chromium.googlesource.com/chromium/src/+/main/content/browser/loader/navigation_url_loader_impl.cc)

## UI 和原生操作契约

独立 UI 使用保留的虚拟 HTTPS origin `https://idv-login.invalid`。其文档响应由当前 BiDi session 的 request interception 提供，不访问 DNS/公网，不部署网站，也不新建应用 HTTP API 端口。

只有单个主页面可以调用原生接口。预注入的 `fetch` 适配器把 `/_idv-login/*` 请求通过 BiDi channel 送到 Python，再调用原 `LocalRequestHandler.handle_simple`。GET query、POST JSON、异步任务轮询、AbortSignal 和 UTF-8 正文保留。响应回到发起请求的 realm，页面已销毁则丢弃，不能泄露给下一页。

边界：精确 origin、顶层主 context、真实发起 realm、方法与路径校验；拒绝 iframe/popup 的原生请求；页面响应禁止 framing/object，关闭本 UI 的 service workers。供应商登录 session 没有 UI router，也没有原生文件/进程能力。
外部新闻/帮助链接打开系统默认浏览器，不允许它替换有特权的 UI 页面。普通图片走浏览器 HTTPS 请求，专用 profile 禁用系统代理，替代旧的 `idvlogin://cdn/` 代理。

以下接口仍由原处理器执行，未移动到浏览器或改成假按钮：
- 账号列表、导入/删除/重命名、默认账号、QR、网页登录和状态轮询。
- 游戏/分发列表，安装、更新、目录定位、本地安装记录、启动和快捷方式。
- 文件/目录选择，路径检查，原生任务、下载进度及暂停/恢复/取消。
- Fever 导入和平台桥配置、云同步、日志导出、诊断/重启和代理设置。
- 账号自动关闭、游戏自动启动、扫码记录、登录延迟等设置。

窗口拖动/最大化改用浏览器原生标题栏，不再假装可以拖动宿主 frameless HWND。后端能力声明为 false，前端先检查能力。关闭浏览器 UI 不关闭后台代理/下载；后续 IPC/URI 激活重新打开或聚焦自有 UI。
main 的现有更新提示和控制窗口仍为原生 Qt。源码没有独立 `QSystemTrayIcon` 调用，不为不存在的托盘功能新增框架。

## 渠道覆盖

| 当前入口 | 实际依赖 | 迁移方式 |
| --- | --- | --- |
| OPPO | MainWorld `HeytapNativeApi`、console RPC、验证 popup、同 profile cookies、向原页面 JS 回写 | 文档创建前单一有序 preload；popup/context 归属跟踪；验证关闭/成功都回到原页面刷新，不重载一次性回调 |
| Bili | 扫码主流程与 OTP/账号密码网页备用，XHR hook | 扫码不改；网页主世界 hook 保留，不放入隔离 sandbox |
| 4399 | callback 页面 JSON、cookie 元数据 | 读取实际回调 page 的正文，不重新请求；在专用 profile 禁用 Firefox JSON Viewer，保留 domain/path/expiry/HttpOnly/SameSite |
| vivo | 网页回调、持久 cookies、后续 HTTP API | 只导出当前登录 context 中适用于固定 API 的 cookies；按 get/use 目标分别投影，不再读取 Chromium SQLite/加密数据库 |
| 360 | 成功 URL 与 Q/T cookie 同时满足 | URL 成功判断前取 cookies，并在 load 时重判，避免仅早期导航事件时序 |
| QQ | `auth://tauth.qq.com/` code；imgcache fragment token 备用 | 显式禁止 OS 派发并捕获完整 URL；限制回调目标、参数数量，不记录凭据 |
| 小米 | 小米 OAuth code + QQ implicit 登录切换 | 保留原生 QQ 按钮；精确回调及 state 检查；QQ callback fragment 保留 |
| 荣耀 | `honorid://redirect_url` code、PKCE URL、设备记录、后续 API | 显式禁止 OS 派发；固定回调与发起 state 校验；序列化格式不变 |
| 华为 | 扫码、移动 UA 网页、历史账号填充、JS 写入 | HTTP/扫码不改；原生填充工具栏保留，写入当前登录 page |
| UC / 微信 | 原生短信/HTTP 与扫码 | 没有 WebEngine 依赖，不为迁移改写 |

`ExternalPage` 只实现当前适配器实际调用的 `url`、`runJavaScript`、`toPlainText`、`close`，不是新建一个通用 WebEngine 模拟框架。

## 发烧 MPay：不是只打开外部网页

当前 main 的 `mpay.dll` SHA256 固定为 `02d27ad3…b3225c`。静态调用链显示，
`mpay_option_web_verify_is_outer_browser_open=1` 只覆盖验证选择；第三方登录按钮
仍经 `ThirdPartyWebLoginForm` 独立加载 helper，失败后回退到 ActiveX `IWebBrowser2`。
只设置这个 option 或删除 Qt WebEngine 仍不能称为无内嵌浏览器。

本次提供源码构建的 Windows x64 `webview_support_helper.dll`：

1. 实现固定 SDK 实际 delay-import 的全部 11 个 C 导出，额外 5 个宿主接口仅供 Python；
   使用普通已存在的 DLL 边界，不做指令 patch、IAT hook 或复制供应商 JS/登录协议。
2. 固定 SDK 的 ThirdPartyWebLoginForm 在 Create 之前真实调用 ClearBrowserData。先记录这项请求，不提前打开浏览器；随后用全新的临时 profile 创建，cookies / localStorage / cache 均为空，而不是页面发请求后才删 cookie。未请求清除的其他实际页面仍使用独立持久 profile。
3. SDK 传入 URL，helper 通知 Python 建独立 Firefox；文档创建前只安装 `mwsInvoke` 传输。
   页面完成后调用 SDK 原加载回调，由 SDK 自己提供完整 bridge JS；原始 JSON 仍由 SDK 消费，
   login callback → GetUserTicket → Fever IPC 不变，不伪造账号字段/成功事件。
4. URL/脚本按 UTF-8，SDK 回调在原 Qt/SDK 线程；回应绑定确切 realm，旧页销毁/导航后丢弃；失败导航只恢复经 Firefox 确认仍存活的旧 realm，不重复调用 SDK Loaded。
   校验真实 MPay HMODULE、宿主 generation、原始 opener 系谱；同映像重叠 controller 同步撤销，
   不让旧回调落到 SDK 的新 module-global controller。
5. 浏览器用户关闭会向拥有的 SDK holder 发 `WM_CLOSE`；SDK Destroy 则先撤销回调再关闭浏览器。
   非 UI 线程 Destroy 不触碰 Qt 对象。MPay 切游戏继续沿用原本的映像驻留/退休规则。
6. 预加载安装目录的 hash-verified helper，拒绝同名外来模块。缺少/不匹配/运行失败时可见失败，
   不恢复嵌入式回退。构建时用 MSVC `/MT`，检查 x64 / 精确导出及无 renderer/COM/动态 CRT 导入。
7. 派生 skin 只修改原 QR 入口与 `layout/webview.xml` 的 eager `WebBrowser` 为普通控件；
   保留 `webview_cef.xml` 中 SDK 必需的原生 `WebviewControl` 占位包装，helper 不创建子渲染器。
8. 丢弃 Python 侧任意 SDK 日志内容；按固定 DLL 的实际 ABI 设置 `vlog_writefile` byte false、
   `plog_level` int32 0，避免已知 SDK JSON / HTTP payload 写入原生日志。不能外推到未来 SDK 或系统崩溃转储。

跨来源 OAuth 页面可以正常导航，但只有 SDK 初始/显式 `LoadUrl` 来源有 SDK bridge 权限。
不会把所有 302 目标自动变成可信来源，也不猜一个域名白名单。固定 DLL 构造
service base + `/api/users/login/pc/oauth`，供应商往返在服务端；不同服务端配置是否需新的
可信来源必须实际验收。未知来源请求 native bridge 会明确取消，不静默卡住。

这属于版本锁定的可审计适配，不是已取得供应商公开稳定 SDK 头文件。
[准确 ABI 证据、限制及验收项目](../native/mpay_browser_adapter/ABI.md) 和
[构建 / 生命周期说明](../native/mpay_browser_adapter/README.md) 随源码提交。

## 登录状态、进程和首次使用

- UI 与每个账号分别使用自己的 Firefox profile，不附着用户日常 profile，不读其密码/书签/cookies。
- 原账号 JSON 字段和刷新协议继续兼容。vivo 增加可选 `cookieRecords`，保留原 `cookies` 字段并兼容旧记录；新记录分别按 get/use 的 URL 选取 cookies，不把不同 path 的同名值压成字典。旧 Qt profile 不删除，但不同引擎的 profile 不直接复制；需要网页登录时可能首次重新认证。
- 只有实际消费 cookies 的 vivo / 360 与需要观测元数据的 4399 配置导出策略；UI、MPay 及其他渠道不导出通用 cookie 快照。策略限制来源、目标域、path、Secure、expiry 和名称，360 只取 Q/T；同名歧义不猜先后顺序，直接失败。来自不同 top-site 的分区、第三方域、用户手动新建无 opener 页面不能成为登录结果。
- 成功事件的 cookies 与 page / context / navigation / revision 绑定，异步 4399 正文读取也绑定原文档。只有运行时接受该 token 后才交付结果；后续页面或关闭阶段不会再次查询并覆盖成功快照，先前导出失败会撤销待提交结果。
- 持久 cookie 留在 Firefox；session cookie 使用 Firefox 原生 sessionstore 保存，保留完整 `originAttributes` / partition / SameSite 等元数据，绝不把无分区标签的 BiDi 快照写回默认 cookie jar。
- 启动前持有应用生命周期锁及 Firefox 原生 profile 锁，先逐级拒绝符号链接/junction，再原子净化全部已知恢复/回退文件，只保留原生 cookies 和一个 `about:blank` tab。关闭窗口、崩溃恢复、旧 callback/history/form 不重放。随机内部 sentinel 确认恢复完成后才允许第一次供应商导航。
- 原生 sessionstore 不是稳定的公共 API。只接受已核验的 `mozLz40` / schema 1；不认识的文件结构明确要求重新登录，不猜测分区归属。未来 Firefox 主版本在打开 profile 前拒绝，不能用 ready 屏障掩盖可能新增的恢复源。验证针对普通 Firefox 153.5.1 ESR 与 158.0.1。I/O、锁或准备失败则禁止启动。
- 强制退登先写持久意图标记，再删除实时 cookies。原生 snapshot 中的随机 witness 证明其在清除之后生成；否则下次启动连 SQLite 持久 cookie 也先清除，再导航。覆盖“标记已落盘、delete 尚未发生就崩溃”的窗口，并保留清除后新登录的状态。
- Windows Python 3.12 的 `mkdir(0700)` 不提供私有 DACL，故给专用目录明确当前 SID / SYSTEM / Administrators 的继承 ACL；Unix 目录为 0700、原子临时文件为 0600。
- 不持久登录使用临时 profile，退出清理。每个会话只拥有自己启动的进程，正常关闭后才完成渠道回调；重复关闭/启动中取消收敛到同一结束路径。
- Windows 版本预检显式 `--wait-for-browser`，保持管理员宿主下的可等待子进程与 stdout；实际 BiDi 启动的 `--remote-debugging-port` 已使官方 launcher 进入等待/继承 pipes/kill-on-close job 路径。job 是浏览器的 best-effort 机制，不把单独 launcher 退出当作绝对的浏览器退出证明：结束前还等待继承的 stdout 真正 EOF，并确认 Firefox 原生 profile 锁已释放；未能确认时保留应用资料锁并提示关闭该工具窗口。
- Firefox 使用随机 loopback BiDi 端口。它没有认证/加密，不能抵御已能以同用户执行代码的恶意进程；不能宣称“没有端口”。不放宽 Origin/Host 白名单，不开启 Gecko 系统访问，不忽略证书错误，不禁用内容 sandbox。
- 未安装/过旧/策略禁止时，原生对话框仍可用，提供官方页面、重试和取消。不会自动安装，不要求设为默认浏览器，不注册全局 `auth` 或 `honorid` 处理器。

## 前端部署和构建

伴随修改位于 `idv-login-webui` fever：识别虚拟 HTTPS origin 的外链与视觉缓存，并根据宿主能力禁用旧标题栏手势。仍兼容游戏 HTTP 页面以及旧版本 `idvlogin:` 前端环境。

前端既有工作流对 push/PR 运行检查，仅 fever 分支非 PR 的提交会将单文件页面写入后端 `assets/cloudRes.json` 的 `login_base64_page_fever`。PR 本身不部署。应先合入并等待前端既有部署，再合后端；不要把本地 `dist` 或临时下载产物提交到任一仓库。

后端 `requirements.txt` 移除 PyQt6-WebEngine，增加小型 `lz4` 解码原生恢复文件，不增加浏览器驱动 Python/Node 依赖。Windows embed Python 和 macOS PyInstaller 仍按各自流程安装同一 requirements。与单独的 Windows Qt 瘦身 PR 是独立变更，不依赖或合并其分支。

## 验证记录和限制

已运行的检查与未运行的验收必须区分：

- Python `compileall src`；前端既有 60 项测试、16 个 SFC 检查、logic 检查、单文件 build。关联 [前端 PR #3](https://github.com/KKeygen/idv-login-webui/pull/3) 的 push / pull_request CI 均成功，部署步骤跳过。
- 官方 Firefox 153.5.1 ESR 与 158.0.1 Linux 云端合成探针，下载 SHA256 与 Mozilla 校验文件一致；未访问供应商账号。
- 实际 `browser_runtime.py` 验证：MainWorld preload、UTF-8 GET/POST、iframe/window.open 回调、302 query+fragment、单次 JSON 正文、创建 popup 立即关闭、旧 realm 回包、HttpOnly session cookie 重启恢复、localStorage、强制退登、启动即取消与自有进程回收。
- 原生 profile 模块实际探针：同名三分区 cookie 原样保存/恢复、并发 lease 拒绝、旧一次性 callback 零重放、未知 schema 提示、symlink 祖先拒绝、清除后新登录保留，以及清除前后两个崩溃窗口不复活 session / persistent cookie。
- 实际 Firefox 的 live-cookie 探针验证 selected context 的分区、第三方域排除、host-only/domain、expiry、get/use path 分离、同名冲突失败并回收进程，以及 360 的 Q/T 限定。Qt 合成事件检查跨 popup 交错、4399 异步 token、关闭先于提交确认、迟到快照、先前导出失败与 transport 关闭抛错后的自有子进程回收。
- 假 SDK + 原生 Qt + 实际 Firefox 验证 Python 创建/加载、SDK 脚本、`mwsInvoke`、SDK 回复往返、Qt 主线程回调、无 opener 窗口拒绝、真实 browsing-context 关闭和跨线程 Destroy。这不覆盖真实 DLL ABI、ctypes 调用约定、HWND 校验或厂商 SDK 的重入行为。
- 原生 Qt offscreen 验证未装 Firefox 的提示、重试、取消以及渠道只完成一次。
- 没有新增仓库单元测试，没有运行完整代理/证书/hosts 主流程，没有在用户设备安装或实验。
- 合成传输通过不等于真实供应商认证通过。Windows/macOS 普通安装版、组织策略、风控/验证码、跨游戏 MPay 登录仍须实际平台验收；不能把编译或 Linux 合成结果称为这些验收。
