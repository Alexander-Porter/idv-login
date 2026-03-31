#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热更新配置编辑脚本

用于安全地编辑 assets/cloudRes.json 中的 hotfix 配置。
自动处理去重：同一模块覆盖相同版本时，只保留最新的。

用法:
    python tools/edit_hotfix.py add --module "模块路径" --commit "sha" --versions "v1,v2" --note "说明"
    python tools/edit_hotfix.py list
    python tools/edit_hotfix.py remove --module "模块路径"
    python tools/edit_hotfix.py remove --version "v5.9.0-beta"
"""

import argparse
import json
import os
import sys
import time
from typing import List, Set

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CLOUDRES_PATH = os.path.join(REPO_ROOT, "assets", "cloudRes.json")


def load_cloudres() -> dict:
    """加载 cloudRes.json"""
    with open(CLOUDRES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cloudres(data: dict):
    """保存 cloudRes.json，保持格式"""
    data["lastModified"]=int(time.time())
    with open(CLOUDRES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✓ 已保存到 {CLOUDRES_PATH}")


def list_hotfixes(data: dict):
    """列出所有 hotfix"""
    hotfixes = data.get("hotfix", [])
    if not hotfixes:
        print("当前没有 hotfix 配置")
        return
    
    print(f"\n当前 hotfix 配置 ({len(hotfixes)} 条):\n")
    for i, hf in enumerate(hotfixes, 1):
        versions = hf.get("need_hotfix_version", [])
        if isinstance(versions, str):
            versions = [versions]
        print(f"[{i}] 模块: {hf.get('target_module', 'N/A')}")
        print(f"    Commit: {hf.get('target_commit', 'N/A')[:12]}...")
        print(f"    版本: {', '.join(versions)}")
        print(f"    说明: {hf.get('note', 'N/A')}")
        print()


def add_hotfix(data: dict, module: str, commit: str, versions: List[str], note: str) -> dict:
    """
    添加 hotfix，自动去重。
    
    去重规则：如果已存在相同 module 且版本有交集的条目，从旧条目移除重复版本。
    如果旧条目版本列表变空，则删除该条目。
    """
    if "hotfix" not in data:
        data["hotfix"] = []
    
    hotfixes = data["hotfix"]
    new_versions_set: Set[str] = set(versions)
    
    # 处理去重
    entries_to_remove = []
    for i, hf in enumerate(hotfixes):
        if hf.get("target_module") != module:
            continue
        
        old_versions = hf.get("need_hotfix_version", [])
        if isinstance(old_versions, str):
            old_versions = [old_versions]
        
        old_versions_set = set(old_versions)
        overlap = old_versions_set & new_versions_set
        
        if overlap:
            # 有重叠，从旧条目移除重叠版本
            remaining = old_versions_set - overlap
            if remaining:
                hf["need_hotfix_version"] = sorted(remaining)
                print(f"⚠ 从旧条目移除版本 {sorted(overlap)}，保留 {sorted(remaining)}")
            else:
                # 旧条目版本全部被覆盖，标记删除
                entries_to_remove.append(i)
                print(f"⚠ 旧条目 (commit: {hf.get('target_commit', '')[:12]}...) 被完全覆盖，将删除")
    
    # 删除被完全覆盖的条目（从后往前删除以保持索引正确）
    for i in reversed(entries_to_remove):
        del hotfixes[i]
    
    # 添加新条目
    new_entry = {
        "need_hotfix_version": sorted(versions),
        "target_module": module,
        "target_commit": commit,
        "note": note
    }
    hotfixes.append(new_entry)
    print(f"✓ 已添加 hotfix: {module} ({commit[:12]}...) -> {versions}")
    
    return data


def remove_hotfix_by_module(data: dict, module: str) -> dict:
    """删除指定模块的所有 hotfix"""
    if "hotfix" not in data:
        print("没有 hotfix 配置")
        return data
    
    original_count = len(data["hotfix"])
    data["hotfix"] = [hf for hf in data["hotfix"] if hf.get("target_module") != module]
    removed = original_count - len(data["hotfix"])
    
    if removed > 0:
        print(f"✓ 已删除 {removed} 条 hotfix (模块: {module})")
    else:
        print(f"未找到模块 {module} 的 hotfix")
    
    return data


def remove_hotfix_by_version(data: dict, version: str) -> dict:
    """删除覆盖指定版本的 hotfix（从所有条目中移除该版本）"""
    if "hotfix" not in data:
        print("没有 hotfix 配置")
        return data
    
    modified = 0
    entries_to_remove = []
    
    for i, hf in enumerate(data["hotfix"]):
        versions = hf.get("need_hotfix_version", [])
        if isinstance(versions, str):
            versions = [versions]
        
        if version in versions:
            new_versions = [v for v in versions if v != version]
            if new_versions:
                hf["need_hotfix_version"] = new_versions
                modified += 1
            else:
                entries_to_remove.append(i)
    
    for i in reversed(entries_to_remove):
        del data["hotfix"][i]
    
    total_affected = modified + len(entries_to_remove)
    if total_affected > 0:
        print(f"✓ 已从 {total_affected} 条 hotfix 中移除版本 {version}")
        print(f"  - 修改: {modified} 条")
        print(f"  - 删除: {len(entries_to_remove)} 条")
    else:
        print(f"未找到覆盖版本 {version} 的 hotfix")
    
    return data


def main():
    parser = argparse.ArgumentParser(description="编辑 cloudRes.json 的 hotfix 配置")
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # add 命令
    add_parser = subparsers.add_parser("add", help="添加 hotfix")
    add_parser.add_argument("--module", "-m", required=True, help="目标模块路径")
    add_parser.add_argument("--commit", "-c", required=True, help="目标 commit SHA")
    add_parser.add_argument("--versions", "-v", required=True, help="影响版本，逗号分隔")
    add_parser.add_argument("--note", "-n", required=True, help="更新说明")
    
    # list 命令
    subparsers.add_parser("list", help="列出所有 hotfix")
    
    # remove 命令
    remove_parser = subparsers.add_parser("remove", help="删除 hotfix")
    remove_parser.add_argument("--module", "-m", help="按模块删除")
    remove_parser.add_argument("--version", "-v", help="按版本删除")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    data = load_cloudres()
    
    if args.command == "list":
        list_hotfixes(data)
    
    elif args.command == "add":
        versions = [v.strip() for v in args.versions.split(",") if v.strip()]
        if not versions:
            print("错误: 版本列表不能为空")
            sys.exit(1)
        
        if len(args.commit) != 40:
            print(f"警告: commit SHA 长度为 {len(args.commit)}，通常应为 40 位")
        
        data = add_hotfix(data, args.module, args.commit, versions, args.note)
        save_cloudres(data)
    
    elif args.command == "remove":
        if not args.module and not args.version:
            print("错误: 必须指定 --module 或 --version")
            sys.exit(1)
        
        if args.module:
            data = remove_hotfix_by_module(data, args.module)
        if args.version:
            data = remove_hotfix_by_version(data, args.version)
        
        save_cloudres(data)


if __name__ == "__main__":
    main()
