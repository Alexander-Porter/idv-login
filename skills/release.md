# 发版技能指南 (Release Skill Guide)

本文档指导 LLM 助手如何执行 idv-login 项目的发版流程。

## 前置检查

在开始发版前，确认以下事项：
1. 当前分支是 `main`
2. 工作区干净（无未提交的更改）
3. 用户已确认要发布的版本号和类型（stable/beta）

## 版本号规则

- 格式：`v{Major}.{Minor}.{Patch}[-{suffix}]`
- 后缀类型：
  - `-stable`：正式版本，面向所有用户
  - `-beta`：测试版本，面向测试用户
  - `-mac-stable`：仅 macOS 的正式版本
- 示例：`v5.9.2-stable`, `v5.10.0-beta`

## 发版步骤

### 步骤 1: 确定版本号

询问用户：
- 新版本号是什么？
- 是 stable 还是 beta？
- 主要更新内容是什么？

### 步骤 2: 更新 version.txt

文件路径：`assets/version.txt`

需要更新以下 4 处版本号（假设新版本是 `5.9.2`）：

```python
filevers=(5, 9, 2, 0),      # 行 6
prodvers=(5, 9, 2, 0),      # 行 7
StringStruct('FileVersion', '5.9.2.0'),     # 行 31
StringStruct('ProductVersion', '5.9.2.0')   # 行 36
```

**注意**：元组格式是 `(Major, Minor, Patch, 0)`，字符串格式是 `'Major.Minor.Patch.0'`

### 步骤 3: 创建 CHANGELOG 文件

文件路径：`ext/v{版本号}-{suffix}-CHANGELOG`

例如：`ext/v5.9.2-stable-CHANGELOG`

**CHANGELOG 模板**：

```markdown
# idv-login登录助手 v{版本号}-{suffix} 更新日志

## v{版本号} 新功能
[·] 功能描述1
[·] 功能描述2

## v{版本号} 问题修复
[·] 修复问题描述1
[·] 修复问题描述2

## 历史版本更新日志

### v{上一版本} 新功能
（从上一个 CHANGELOG 复制相关内容）
```

**格式要点**：
- 使用 `[·]` 作为列表前缀（不是 `-` 或 `*`）
- 新功能和问题修复分开列出
- 包含历史版本信息供用户参考

### 步骤 4: 提交更改

```bash
git add assets/version.txt
git add ext/v{版本号}-{suffix}-CHANGELOG
git commit -m "chore: release v{版本号}-{suffix}"
```

### 步骤 5: 创建并推送 Tag

```bash
git tag v{版本号}-{suffix}
git push origin main
git push origin v{版本号}-{suffix}
```

### 步骤 6: 验证发布

1. 打开 GitHub Actions 页面确认 `build-stable.yaml` workflow 已触发
2. 等待构建完成（约 15-30 分钟）
3. 检查 GitHub Releases 页面确认发布成功
4. 检查夸克网盘和 Gitee 同步状态

## 快速参考

### 需要修改的文件清单

| 文件 | 修改内容 |
|------|----------|
| `assets/version.txt` | 更新 4 处版本号 |
| `ext/v{ver}-{suffix}-CHANGELOG` | 新建，写入更新日志 |

### Git 命令序列

```bash
# 完整发版命令序列（替换 {VERSION} 为实际版本如 v5.9.2-stable）
git add assets/version.txt ext/{VERSION}-CHANGELOG
git commit -m "chore: release {VERSION}"
git tag {VERSION}
git push origin main
git push origin {VERSION}
```

## 回滚指南

如果发版出现问题：

```bash
# 删除本地 tag
git tag -d v{版本号}-{suffix}

# 删除远程 tag（会取消 GitHub Actions）
git push origin --delete v{版本号}-{suffix}

# 回滚 commit
git revert HEAD
git push origin main
```

## 常见问题

### Q: CHANGELOG 文件名格式是什么？
A: `v{Major}.{Minor}.{Patch}-{stable|beta}-CHANGELOG`，无文件扩展名

### Q: version.txt 里的版本号需要带 `v` 前缀吗？
A: 不需要，纯数字格式如 `5.9.2.0`

### Q: 如何判断是 stable 还是 beta？
A: 问用户。一般来说：
- 新功能上线先发 beta 测试
- 测试稳定后再发 stable
- 紧急 bug 修复可直接发 stable

### Q: 可以跳过版本号吗？
A: 可以，版本号不要求连续，但要大于当前最新版本
