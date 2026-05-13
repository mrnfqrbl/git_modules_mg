#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
git_modules_mg 命令行入口
=========================
用法：
    python main.py add <url>          添加模块到待迁移清单（submod.json）
    python main.py add <url1> <url2>  批量添加
    python main.py run                执行迁移（处理 submod.json 中尚未迁移的条目）
    python main.py run --dry-run      只做计划不执行
    python main.py run --only <url>   只处理指定条目（不看清单）
    python main.py refresh <url>      刷新指定条目（从缓存中删除，下次 run 时重新处理）
    python main.py refresh --all      刷新全部缓存
    python main.py list               列出当前清单和缓存状态
    python main.py update             迁移完成后更新根仓库（添加子模块+推送）

配置：
    config.ini 中需要配置 gitee token 和根仓库路径等信息。
    submod.json / submod_data.json 由本工具自动维护，位于根仓库目录下。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 确保 lib/ 可被导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.main_api import MainApi
from lib.缓存管理 import 模块清单, 处理缓存, 过滤待处理列表
from lib.子仓库管理 import 批量迁移
from lib.git_command import Git工具


# ─────────────────────────────────────────────
# 路径计算
# ─────────────────────────────────────────────
def _获取根目录() -> str:
    """本脚本所在目录即为项目根目录"""
    return os.path.dirname(os.path.abspath(__file__))


def _获取清单路径(根目录: str) -> str:
    return os.path.join(根目录, "submod.json")


def _获取缓存路径(根目录: str) -> str:
    return os.path.join(根目录, "submod_data.json")


def _获取缓存仓库目录(根目录: str, config_值: str = "") -> str:
    """缓存克隆目录（默认 根目录/.cache）"""
    if config_值 and os.path.isabs(config_值):
        return config_值
    return os.path.join(根目录, ".cache")


# ─────────────────────────────────────────────
# 子命令：add
# ─────────────────────────────────────────────
def cmd_add(args, 根目录: str):
    """添加模块到 submod.json"""
    清单 = 模块清单(_获取清单路径(根目录))

    for url in args.urls:
        url = url.strip()
        if not url:
            continue
        if 清单.添加模块(url):
            print(f"  ✓ 已添加：{url}")
        else:
            print(f"  - 已存在，跳过：{url}")

    print(f"\n当前清单共 {清单.数量()} 个模块")


# ─────────────────────────────────────────────
# 子命令：run
# ─────────────────────────────────────────────
def cmd_run(args, 根目录: str):
    """执行迁移"""
    # 初始化 API（读取 config.ini 中的 token）
    try:
        api = MainApi(debug=args.debug)
    except Exception as e:
        print(f"✗ 初始化失败：{e}")
        print("  请检查 config.ini 中的 gitee token 是否正确")
        sys.exit(1)

    if not api.tokens.get("gitee"):
        print("✗ 未配置有效的 gitee token")
        print("  请在 config.ini 的 [gitee] 节设置 token，或设置环境变量 GITEE_TOKEN")
        sys.exit(1)

    # 获取 gitee 用户名
    try:
        gitee用户名 = api.gitee_api.获取当前用户名()
    except Exception as e:
        print(f"✗ 获取 gitee 用户名失败：{e}")
        sys.exit(1)

    print(f"  Gitee 用户：{gitee用户名}")

    # 确定待处理列表
    if args.only:
        # --only 模式：不看清单，直接处理指定 URL
        待处理 = [url.strip() for url in args.only]
        print(f"  --only 模式，处理 {len(待处理)} 个指定条目")
    else:
        # 正常模式：从清单过滤
        清单 = 模块清单(_获取清单路径(根目录))
        缓存 = 处理缓存(_获取缓存路径(根目录))

        if 清单.数量() == 0:
            print("✗ 模块清单为空，请先用 add 命令添加模块")
            print(f"  用法：python main.py add <url>")
            sys.exit(0)

        待处理 = 过滤待处理列表(清单, 缓存)
        print(f"  清单共 {清单.数量()} 个模块，本次待处理 {len(待处理)} 个")

    if not 待处理:
        print("\n✓ 无需处理的条目（全部已完成或跳过）")
        sys.exit(0)

    print(f"\n{'─' * 50}")
    print(f"  开始迁移（{'dry-run 模式' if args.dry_run else '实际执行'}）")
    print(f"{'─' * 50}\n")

    # 读取配置中的缓存目录
    缓存目录配置 = ""
    try:
        缓存目录配置 = api.config.get("迁移", "缓存目录")
    except Exception:
        pass
    缓存仓库目录 = _获取缓存仓库目录(根目录, 缓存目录配置)

    # 读取白名单域名
    白名单域名 = ["gitee.com", "openi.pcl.ac.cn"]
    try:
        白名单配置 = api.config.get("迁移", "白名单域名")
        if 白名单配置:
            白名单域名 = [d.strip() for d in 白名单配置.split(",") if d.strip()]
    except Exception:
        pass

    # 执行批量迁移
    结果 = 批量迁移(
        待处理列表=待处理,
        gitee_api=api.gitee_api,
        gitee用户名=gitee用户名,
        缓存根目录=缓存仓库目录,
        目标域名列表=["gitee.com"],
        白名单域名=白名单域名,
        dry_run=args.dry_run,
        logger=api.logger,
    )

    # 写入缓存
    if 结果.状态 and 结果.数据 and not args.dry_run:
        映射表 = 结果.数据.get("映射表", {})
        if 映射表:
            缓存 = 处理缓存(_获取缓存路径(根目录))
            缓存.批量记录(映射表)
            print(f"\n  缓存已更新（新增 {len(映射表)} 条记录）")

    # 输出结果
    print(f"\n{'═' * 50}")
    if 结果.状态 and 结果.数据:
        数据 = 结果.数据
        print(f"  迁移完成：总计 {数据['总数']} | 成功 {数据['成功']} | 失败 {数据['失败']}")
        if 数据.get("映射表"):
            print(f"\n  映射关系：")
            for 旧, 新 in 数据["映射表"].items():
                print(f"    {旧}")
                print(f"      → {新}")
    else:
        print(f"  迁移结果：{结果.错误信息}")
    print(f"{'═' * 50}")


# ─────────────────────────────────────────────
# 子命令：refresh
# ─────────────────────────────────────────────
def cmd_refresh(args, 根目录: str):
    """刷新缓存（删除指定/全部条目，下次 run 重新处理）"""
    缓存 = 处理缓存(_获取缓存路径(根目录))

    if args.all:
        缓存.刷新全部()
        print("  ✓ 已清空全部缓存")
        return

    if not args.urls:
        print("✗ 请指定要刷新的 URL，或使用 --all 清空全部")
        sys.exit(1)

    for url in args.urls:
        if 缓存.刷新(url):
            print(f"  ✓ 已刷新：{url}")
        else:
            print(f"  - 未找到：{url}")

    print(f"\n缓存中剩余 {缓存.数量()} 条记录")


# ─────────────────────────────────────────────
# 子命令：list
# ─────────────────────────────────────────────
def cmd_list(args, 根目录: str):
    """列出清单和缓存状态"""
    清单 = 模块清单(_获取清单路径(根目录))
    缓存 = 处理缓存(_获取缓存路径(根目录))

    print(f"\n{'═' * 50}")
    print(f"  模块清单（submod.json）：{清单.数量()} 个")
    print(f"{'─' * 50}")
    for 条目 in 清单.模块列表:
        url = 条目.get("url", "")
        已处理标记 = "✓" if 缓存.是否已处理(url) else "○"
        新url = 缓存.获取新url(url) or ""
        print(f"  [{已处理标记}] {url}")
        if 新url:
            print(f"        → {新url}")

    print(f"\n{'─' * 50}")
    print(f"  已处理缓存（submod_data.json）：{缓存.数量()} 条")
    print(f"{'═' * 50}")


# ─────────────────────────────────────────────
# 子命令：update
# ─────────────────────────────────────────────
def cmd_update(args, 根目录: str):
    """迁移完成后，更新根仓库（添加子模块 + 推送到所有远程）"""
    缓存 = 处理缓存(_获取缓存路径(根目录))

    if 缓存.数量() == 0:
        print("✗ 缓存为空，请先执行 run 命令完成迁移")
        sys.exit(0)

    # 读取根仓库路径
    根仓库路径 = ""
    try:
        api = MainApi(debug=args.debug)
        根仓库路径 = api.config.get("迁移", "根仓库路径")
    except Exception:
        pass

    if not 根仓库路径 or not os.path.isdir(根仓库路径):
        print("✗ 根仓库路径未配置或无效")
        print("  请在 config.ini 的 [迁移] 节设置 根仓库路径")
        sys.exit(1)

    # 检查根仓库有效性
    有效性 = Git工具.是否为有效仓库(根仓库路径)
    if not 有效性.状态 or not 有效性.数据:
        print(f"✗ 不是有效的 Git 仓库：{根仓库路径}")
        sys.exit(1)

    仓库 = Git工具(根仓库路径)
    映射表 = 缓存.获取所有映射()

    print(f"\n  根仓库：{根仓库路径}")
    print(f"  待更新子模块：{len(映射表)} 个")
    print(f"{'─' * 50}")

    # 获取当前子模块列表
    子模块结果 = 仓库.获取子模块列表()
    现有子模块 = {}
    if 子模块结果.状态 and 子模块结果.数据:
        现有子模块 = {s["URL"]: s for s in 子模块结果.数据}

    # 对映射表中的每一项：如果旧 URL 在子模块列表里 → 删除旧 + 添加新
    for 旧url, 新url in 映射表.items():
        if 旧url in 现有子模块:
            模块信息 = 现有子模块[旧url]
            名称 = 模块信息["名称"]
            路径 = 模块信息["路径"]
            分支 = 模块信息.get("追踪分支")

            print(f"  替换子模块：{名称}")
            print(f"    {旧url} → {新url}")

            if not args.dry_run:
                # 删除旧
                仓库.删除子模块(名称)
                # 添加新
                仓库.添加子模块(名称, 路径, 新url, 分支=分支)

    # 提交
    if not args.dry_run:
        脏 = 仓库.是否有未提交更改()
        if 脏.状态 and 脏.数据:
            仓库.提交(提交信息="[git_modules_mg] 更新子模块引用至 gitee", 是否允许自动add=True)
            print(f"\n  ✓ 已提交变更")

            # 推送到所有远程（强制）
            try:
                remotes = [r.name for r in 仓库.repo.remotes]
                for remote_name in remotes:
                    仓库.推送(远程名称=remote_name, 强制=True)
                    print(f"  ✓ 已推送到 {remote_name}")
            except Exception as e:
                print(f"  ⚠ 推送异常：{e}")
        else:
            print(f"\n  - 无变更需要提交")
    else:
        print(f"\n  [dry-run] 跳过提交和推送")


# ─────────────────────────────────────────────
# 参数解析
# ─────────────────────────────────────────────
def main():
    根目录 = _获取根目录()

    parser = argparse.ArgumentParser(
        prog="git_modules_mg",
        description="Git 仓库批量迁移与子模块管理工具",
    )
    parser.add_argument("--debug", action="store_true", help="启用调试日志")

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # add
    add_parser = subparsers.add_parser("add", help="添加模块到待迁移清单")
    add_parser.add_argument("urls", nargs="+", help="要添加的仓库 URL")

    # run
    run_parser = subparsers.add_parser("run", help="执行迁移")
    run_parser.add_argument("--dry-run", action="store_true", help="只做计划不执行")
    run_parser.add_argument("--only", nargs="+", help="只处理指定 URL（不看清单）")
    run_parser.add_argument("--debug", action="store_true", help="调试模式")

    # refresh
    refresh_parser = subparsers.add_parser("refresh", help="刷新缓存（重新处理指定模块）")
    refresh_parser.add_argument("urls", nargs="*", help="要刷新的 URL")
    refresh_parser.add_argument("--all", action="store_true", help="清空全部缓存")

    # list
    subparsers.add_parser("list", help="列出清单和缓存状态")

    # update
    update_parser = subparsers.add_parser("update", help="更新根仓库子模块引用并推送")
    update_parser.add_argument("--dry-run", action="store_true", help="只做计划不执行")
    update_parser.add_argument("--debug", action="store_true", help="调试模式")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 分发命令
    命令映射 = {
        "add": cmd_add,
        "run": cmd_run,
        "refresh": cmd_refresh,
        "list": cmd_list,
        "update": cmd_update,
    }

    处理函数 = 命令映射.get(args.command)
    if 处理函数:
        处理函数(args, 根目录)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
