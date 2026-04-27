#!/bin/bash
# idv-login macOS 运行脚本
# 用法: bash <(curl -fsSL https://raw.githubusercontent.com/KKeygen/idv-login/main/run-mac.sh)

set -euo pipefail

INSTALL_DIR="/usr/local/bin"
INSTALL_PATH="$INSTALL_DIR/idv-login"
EXTRACTED_DIR=""
RESOLVED_PATH=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}[信息]${NC} $1"; }
ok()    { echo -e "${GREEN}[完成]${NC} $1"; }
warn()  { echo -e "${YELLOW}[警告]${NC} $1"; }
error() { echo -e "${RED}[错误]${NC} $1"; exit 1; }

# ── 网络恢复提示（异常退出时也显示）──────────────────
cleanup_hint() {
    # 清理解压的临时目录
    if [ -n "$EXTRACTED_DIR" ] && [ -d "$EXTRACTED_DIR" ]; then
        rm -rf "$EXTRACTED_DIR"
    fi
    echo ""
    echo -e "${YELLOW}════════════════════════════════════════${NC}"
    echo -e "${YELLOW} 如果网络异常，请在终端运行以下命令恢复：${NC}"
    echo -e "${YELLOW}════════════════════════════════════════${NC}"
    echo "  networksetup -setwebproxystate Wi-Fi off"
    echo "  networksetup -setsecurewebproxystate Wi-Fi off"
    echo ""
}
trap cleanup_hint EXIT

# ── 架构检测 ──────────────────────────────────────────
check_arch() {
    local is_arm64
    is_arm64=$(sysctl -in hw.optional.arm64 2>/dev/null || echo "0")

    if [ "$is_arm64" != "1" ]; then
        error "当前仅支持 Apple Silicon (ARM64) Mac。\n  如果您使用的是 Intel Mac，暂不支持，敬请期待。"
    fi

    # 检测是否在 Rosetta 翻译环境下运行
    local translated
    translated=$(sysctl -in sysctl.proc_translated 2>/dev/null || echo "0")
    if [ "$translated" = "1" ]; then
        warn "检测到当前终端运行在 Rosetta 翻译模式下，建议使用原生 ARM64 终端"
    fi

    ok "Apple Silicon (ARM64) ✓"
}

# ── 解析拖入的文件路径 ────────────────────────────────
parse_path() {
    local raw="$1"

    # 去除首尾空白
    raw=$(echo "$raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

    # 去除包裹的引号 (单引号或双引号)
    if [[ "$raw" =~ ^\'(.*)\'$ ]]; then
        raw="${BASH_REMATCH[1]}"
    elif [[ "$raw" =~ ^\"(.*)\"$ ]]; then
        raw="${BASH_REMATCH[1]}"
    fi

    # 处理反斜杠转义的空格 (Terminal 拖入时常见)
    raw=$(echo "$raw" | sed 's/\\ / /g')

    echo "$raw"
}

# ── 验证文件 ──────────────────────────────────────────
validate_file() {
    local filepath="$1"

    # 检查文件存在
    if [ ! -e "$filepath" ]; then
        error "文件不存在: $filepath"
    fi

    # 如果是 zip 文件，自动解压
    if [[ "$filepath" == *.zip ]]; then
        info "检测到 zip 文件，正在解压..."
        local tmp_dir
        tmp_dir=$(mktemp -d /tmp/idv-login-XXXXXX)
        unzip -o -q "$filepath" -d "$tmp_dir" || error "解压失败"

        # 在解压目录中查找 idv-login 二进制文件
        local found
        found=$(find "$tmp_dir" -name "idv-login-*" -type f | head -1)
        if [ -z "$found" ]; then
            rm -rf "$tmp_dir"
            error "zip 中未找到 idv-login 可执行文件"
        fi
        ok "已解压: $(basename "$found")"
        filepath="$found"
        EXTRACTED_DIR="$tmp_dir"
    fi

    # 检查是否为目录
    if [ -d "$filepath" ]; then
        error "这是一个文件夹，请拖入文件而非文件夹"
    fi

    # 检查是否为普通文件
    if [ ! -f "$filepath" ]; then
        error "不是有效的文件: $filepath"
    fi

    # 检查文件名是否匹配预期模式
    local basename
    basename=$(basename "$filepath")
    if [[ ! "$basename" == idv-login-* ]]; then
        warn "文件名 '$basename' 不符合预期格式 (idv-login-xxx-mac)"
        echo -ne "  是否继续？(y/N): "
        read -r confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            error "已取消"
        fi
    fi

    # 验证二进制架构
    local file_info
    file_info=$(file "$filepath" 2>/dev/null || echo "unknown")
    if echo "$file_info" | grep -qi "arm64\|aarch64"; then
        ok "文件架构: ARM64 ✓"
    elif echo "$file_info" | grep -qi "x86_64\|x86-64"; then
        error "此文件是 Intel (x86_64) 版本，请下载 ARM64 版本"
    elif echo "$file_info" | grep -qi "Mach-O"; then
        ok "文件类型: macOS 可执行文件 ✓"
    else
        warn "无法确认文件架构，将尝试运行"
    fi

    # 检查文件大小（PyInstaller 打包通常 > 10MB）
    local file_size
    file_size=$(stat -f%z "$filepath" 2>/dev/null || echo "0")
    if [ "$file_size" -lt 1048576 ]; then
        error "文件过小 ($(( file_size / 1024 )) KB)，可能不完整或不是正确的文件"
    fi
    ok "文件大小: $(( file_size / 1048576 )) MB ✓"

    # 将解析后的路径传递回调用者
    RESOLVED_PATH="$filepath"
}

# ── SHA256 完整性校验 ──────────────────────────────────
verify_sha256() {
    local filepath="$1"
    local api_url="https://api.github.com/repos/KKeygen/idv-login/releases/latest"

    info "正在从 GitHub 获取官方校验值..."

    # 获取最新 release 信息
    local release_info
    release_info=$(curl -fsSL "$api_url" 2>/dev/null) || {
        warn "无法访问 GitHub API，跳过校验"
        return 0
    }

    # 从 API 的 digest 字段获取 SHA256 (格式: "sha256:xxxxx")
    local expected_sha
    expected_sha=$(echo "$release_info" | grep -A2 '"name":.*mac"' | grep '"digest"' | head -1 | sed 's/.*"sha256://;s/".*//')

    # 兜底：尝试直接从 assets 数组中匹配
    if [ -z "$expected_sha" ]; then
        expected_sha=$(echo "$release_info" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for asset in data.get('assets', []):
        if 'mac' in asset.get('name', ''):
            digest = asset.get('digest', '')
            if digest.startswith('sha256:'):
                print(digest[7:])
                break
except: pass
" 2>/dev/null)
    fi

    if [ -z "$expected_sha" ]; then
        warn "无法获取官方校验值，跳过校验"
        return 0
    fi

    # 计算本地文件的 SHA256
    local local_sha
    local_sha=$(shasum -a 256 "$filepath" | awk '{print $1}')

    if [ "$local_sha" = "$expected_sha" ]; then
        ok "SHA256 校验通过 ✓"
    else
        echo ""
        echo -e "${RED}════════════════════════════════════════${NC}"
        echo -e "${RED} SHA256 校验失败！文件可能被篡改或版本不匹配${NC}"
        echo -e "${RED}════════════════════════════════════════${NC}"
        echo "  本地文件: $local_sha"
        echo "  官方文件: $expected_sha"
        echo ""
        echo -ne "  是否仍然继续运行？(y/N): "
        read -r confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            error "已取消运行"
        fi
        warn "用户选择继续运行未通过校验的文件"
    fi
}

# ── 准备并运行 ────────────────────────────────────────
prepare_and_run() {
    local filepath="$1"

    # 设置执行权限
    chmod +x "$filepath"

    # 移除 quarantine 属性 (best-effort)
    xattr -d com.apple.quarantine "$filepath" 2>/dev/null || true

    ok "文件已准备就绪"
    echo ""
    info "正在启动 idv-login，请输入电脑密码..."
    echo -e "${YELLOW}  （密码输入时屏幕不会显示字符，这是正常的）${NC}"
    echo ""

    # 运行工具
    sudo "$filepath" || true
}

# ── 提供安装选项 ──────────────────────────────────────
offer_install() {
    local filepath="$1"

    echo ""
    echo -ne "${BLUE}是否将工具安装到系统目录以便下次直接运行？(输入y或N后回车): ${NC}"
    read -r install_choice

    if [[ "$install_choice" =~ ^[Yy]$ ]]; then
        if [ ! -d "$INSTALL_DIR" ]; then
            sudo mkdir -p "$INSTALL_DIR"
        fi
        sudo cp "$filepath" "$INSTALL_PATH"
        sudo chmod +x "$INSTALL_PATH"
        sudo xattr -d com.apple.quarantine "$INSTALL_PATH" 2>/dev/null || true
        ok "已安装到 $INSTALL_PATH"
        echo "  下次运行只需在终端输入: sudo idv-login"
    fi
}

# ── 主流程 ────────────────────────────────────────────
main() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   idv-login macOS 运行助手               ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
    echo ""

    check_arch

    echo ""
    echo -e "${BOLD}请将下载的压缩包或二进制文件拖入此窗口，然后按回车键：${NC}"
    echo -e "  ${YELLOW}（从访达中拖入即可，路径会自动填入）${NC}"
    echo -ne "> "
    read -r raw_path

    # 解析路径
    local filepath
    filepath=$(parse_path "$raw_path")

    if [ -z "$filepath" ]; then
        error "未输入文件路径"
    fi

    info "文件路径: $filepath"

    # 验证文件（zip 会被自动解压，路径可能改变）
    validate_file "$filepath"
    filepath="$RESOLVED_PATH"

    # SHA256 完整性校验
    verify_sha256 "$filepath"

    # 运行
    prepare_and_run "$filepath"

    # 提供安装选项
    offer_install "$filepath"

    echo ""
    ok "感谢使用 idv-login！"
}

main
