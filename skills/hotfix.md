# 热更新技能指南 (Hotfix Skill Guide)

本文档指导 LLM 助手如何为 idv-login 项目添加热更新配置。

## 热更新机制说明

热更新通过 `assets/cloudRes.json` 的 `hotfix` 数组下发，客户端会：
1. 检查当前版本是否在 `need_hotfix_version` 列表中
2. 如果匹配，下载指定 commit 的模块文件替换本地文件
3. 重启程序使修改生效

## 前置信息收集

在添加 hotfix 前，需要向用户确认：
1. **目标模块**：要热更新的模块路径（如 `channelHandler.vivoLogin.vivoChannel`）
2. **目标 commit**：包含修复代码的 commit SHA（完整 40 位）
3. **影响版本**：需要热更新的版本列表（如 `["v5.9.1-stable", "v5.9.0-beta"]`）
4. **更新说明**：简短描述这个热更新的目的

## 添加 Hotfix 步骤

### 步骤 1: 确认 commit 已推送

确保包含修复的 commit 已经推送到远程仓库（Gitee/GitHub），否则客户端无法下载。

```bash
git log --oneline -5  # 查看最近提交
git push origin main  # 确保已推送
```

### 步骤 2: 使用脚本编辑 cloudRes.json

**重要**：不要手动编辑 cloudRes.json，使用 `tools/edit_hotfix.py` 脚本。

```bash
python tools/edit_hotfix.py add \
  --module "channelHandler.vivoLogin.vivoChannel" \
  --commit "759708aaf882c114d5a0fe0fb2e0d583f6d2d677" \
  --versions "v5.9.1-stable,v5.9.0-beta" \
  --note "修复VIVO账号cookies过期问题"
```

脚本会自动：
- 读取现有 cloudRes.json
- 如果同一模块已有 hotfix 覆盖相同版本，**只保留新的**（删除旧的）
- 添加新的 hotfix 条目
- 格式化并保存 JSON

### 步骤 3: 验证并提交

```bash
# 验证 JSON 格式正确
python -m json.tool assets/cloudRes.json > /dev/null && echo "JSON valid"
```

# 询问用户
提交前，必须显式询问用户是否允许提交更改。
使用ask_user/ask_questions/query_user.


# 提交更改
git add assets/cloudRes.json
git commit -m "hotfix: {模块名} - {简短描述}"
git push origin main
```

## Hotfix 条目结构

```json
{
  "need_hotfix_version": ["v5.9.1-stable", "v5.9.0-beta"],
  "target_module": "channelHandler.vivoLogin.vivoChannel",
  "target_commit": "759708aaf882c114d5a0fe0fb2e0d583f6d2d677",
  "note": "修复VIVO账号cookies过期问题"
}
```

| 字段 | 说明 |
|------|------|
| `need_hotfix_version` | 需要应用此热更新的版本列表 |
| `target_module` | Python 模块路径（点分隔，对应 `src/` 下的文件） |
| `target_commit` | 包含修复代码的 commit SHA（完整 40 位） |
| `note` | 更新说明，会显示给用户 |

## 模块路径对照

| 模块路径 | 对应文件 |
|----------|----------|
| `main` | `src/main.py` |
| `channelmgr` | `src/channelmgr.py` |
| `channelHandler.vivoLogin.vivoChannel` | `src/channelHandler/vivoLogin/vivoChannel.py` |
| `channelHandler.oppoLogin.oppoChannel` | `src/channelHandler/oppoLogin/oppoChannel.py` |
| `channelHandler.huaLogin.huaChannel` | `src/channelHandler/huaLogin/huaChannel.py` |
| `channelHandler.WebLoginUtils` | `src/channelHandler/WebLoginUtils.py` |
| `common_mpay_routes` | `src/common_mpay_routes.py` |

## 脚本命令参考

### 添加 hotfix
```bash
python tools/edit_hotfix.py add \
  --module "模块路径" \
  --commit "commit_sha" \
  --versions "v1,v2,v3" \
  --note "说明"
```

### 查看当前 hotfix 列表
```bash
python tools/edit_hotfix.py list
```

### 删除指定模块的 hotfix
```bash
python tools/edit_hotfix.py remove --module "模块路径"
```

### 删除覆盖指定版本的 hotfix
```bash
python tools/edit_hotfix.py remove --version "v5.9.0-beta"
```

## 去重规则

当添加新 hotfix 时，脚本会检查：
- 如果已存在**相同 `target_module`** 且 **`need_hotfix_version` 有交集**的旧条目
- 则从旧条目的 `need_hotfix_version` 中移除重复的版本
- 如果旧条目的版本列表变为空，则删除该条目

这确保同一模块对同一版本只有一个 hotfix 生效（最新添加的）。

## 常见问题

### Q: 如何找到正确的 commit SHA？
A: 使用 `git log --oneline src/path/to/module.py` 查看该文件的提交历史。

### Q: 可以同时热更新多个模块吗？
A: 可以，多次运行 add 命令，每个模块一条记录。

### Q: hotfix 会立即生效吗？
A: 推送后，用户下次启动工具时会检测到并提示更新。

### Q: 如何回滚 hotfix？
A: 从 `hotfix` 数组中删除对应条目并推送，或者用户可以在倒计时期间退出跳过。
