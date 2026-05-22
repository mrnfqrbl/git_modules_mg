#!/usr/bin/env python3
"""gmm - Git Modules Manager 全局 CLI"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.info_texts import get_brief, get_full, get_cmd, get_error
from lib.根仓库注册 import 根仓库注册表
from lib.根仓库定位 import 定位根仓库, 根仓库定位错误
from lib.缓存管理 import 模块清单, 处理缓存, 过滤待处理列表
from lib.main_api import MainApi
from lib.子仓库管理 import 批量迁移
from lib.用户配置 import 解析缓存目录, 解析白名单域名, 加载用户配置, 用户根目录
from lib.git_command import Git工具
from lib.gdm import 函数通用返回模型


# ── 短命令别名映射 ──
短命令别名 = {
    "cfg": "config",
    "ls": "list",
}

所有命令名集合 = set(短命令别名.keys()) | set(短命令别名.values()) | {"--help-full"}


# ─────────────────────────────────────────────
# 解析 name 和 命令
# ─────────────────────────────────────────────
def _解析name和命令(argv: list[str]) -> tuple[str | None, list[str]]:
    """
    判断 argv[0] 是否是已注册的仓库名。
    是 → 返回 (name, argv[1:])
    否 → 返回 (None, argv)
    """
    if not argv:
        return None, argv
    注册表 = 根仓库注册表()
    候选 = argv[0]
    if 候选 in 注册表.仓库表 and 候选 not in 所有命令名集合:
        return 候选, argv[1:]
    return None, argv


# ─────────────────────────────────────────────
# 定位根仓库（统一入口）
# ─────────────────────────────────────────────
def _定位(名称: str | None = None, 路径: str | None = None) -> tuple[str, str]:
    """返回 (名称, 路径)，找不到时直接 exit"""
    try:
        return 定位根仓库(名称, 路径)
    except 根仓库定位错误 as e:
        print(f"✗ {e}")
        sys.exit(1)


# ─────────────────────────────────────────────
# 子命令：gmm repo
# ─────────────────────────────────────────────
def cmd_repo_add(args):
    注册表 = 根仓库注册表()
    路径 = os.path.abspath(args.path)
    if 注册表.注册(args.name, 路径, args.备注 or ""):
        print(f"  ✓ 已注册：{args.name} → {路径}")
    else:
        print(f"  ✗ 注册失败：路径不是有效的 Git 仓库或名称无效")
        sys.exit(1)
def cmd_clean(args, 名称: str, 根仓库路径: str):
    """清空根仓库的所有子模块"""
    仓库 = Git工具(根仓库路径)
    子模块结果 = 仓库.获取子模块列表()
    if not 子模块结果.状态 or not 子模块结果.数据:
        print("  当前仓库没有子模块")
        return

    子模块列表 = 子模块结果.数据
    print(f"  发现 {len(子模块列表)} 个子模块：")
    for 子模块 in 子模块列表:
        print(f"    - {子模块['名称']} @ {子模块['路径']} → {子模块['URL']}")

    if not args.force:
        print(f"\n  ? 使用 --force 确认清空所有子模块")
        return

    for 子模块 in 子模块列表:
        print(f"  删除子模块：{子模块['名称']}...", end=" ")
        结果 = 仓库.删除子模块(子模块["名称"])
        print("✓" if 结果.状态 else f"✗ {结果.错误信息}")

    # 如果有变更则提交
    脏 = 仓库.是否有未提交更改()
    if 脏.状态 and 脏.数据:
        仓库.提交("[gmm] 清空所有子模块", 是否允许自动add=True)
        print(f"\n  ✓ 已提交清空变更")
    else:
        print(f"\n  - 无变更需要提交")


def cmd_sync(args, 名称: str, 根仓库路径: str):
    """从根仓库的现有子模块自动扫描并加入清单"""
    仓库 = Git工具(根仓库路径)
    子模块结果 = 仓库.获取子模块列表()
    if not 子模块结果.状态 or not 子模块结果.数据:
        print("  当前仓库没有子模块")
        return

    清单 = 模块清单(根仓库路径)
    新增数 = 0
    已存在数 = 0
    for 子模块 in 子模块结果.数据:
        url = 子模块["URL"]
        if not url:
            continue
        子模块名 = 子模块["名称"]
        路径 = 子模块["路径"]
        分支 = 子模块.get("追踪分支") or None
        新增 = 清单.添加模块(url, 子模块名=子模块名, 子模块路径=路径, 追踪分支=分支)
        if 新增:
            新增数 += 1
            print(f"  ✓ 新增：{子模块名} → {url}")
        else:
            已存在数 += 1

    print(f"\n  清单共 {清单.数量()} 个模块（新增 {新增数}，已存在 {已存在数}）")

def cmd_repo_remove(args):
    注册表 = 根仓库注册表()
    if 注册表.删除(args.name):
        print(f"  ✓ 已删除：{args.name}")
    else:
        print(f"  ✗ 未找到：{args.name}")
        sys.exit(1)


def cmd_repo_list(args):
    注册表 = 根仓库注册表()
    列表 = 注册表.列出()
    if not 列表:
        print("  (空)")
        return
    for 名称, 路径 in 列表:
        标记 = " [默认]" if 名称 == 注册表.默认名称 else ""
        print(f"  [{名称}]{标记}")
        print(f"    {路径}")


def cmd_repo_default(args):
    注册表 = 根仓库注册表()
    if 注册表.设默认(args.name):
        print(f"  ✓ 已设置默认：{args.name}")
    else:
        print(f"  ✗ 未找到：{args.name}")
        sys.exit(1)


# ─────────────────────────────────────────────
# 子命令：gmm [name] add
# ─────────────────────────────────────────────
def cmd_add(args, 名称: str, 根仓库路径: str):
    清单 = 模块清单(根仓库路径)
    for url in args.urls:
        url = url.strip()
        if not url:
            continue
        新增 = 清单.添加模块(url, 子模块名=args.name_arg, 子模块路径=args.path, 追踪分支=args.branch)
        if 新增:
            print(f"  ✓ 已添加：{url}")
        else:
            print(f"  - 已存在（或已更新）：{url}")
    print(f"  当前清单共 {清单.数量()} 个模块")


# ─────────────────────────────────────────────
# 子命令：gmm [name] run
# ─────────────────────────────────────────────
def cmd_run(args, 名称: str, 根仓库路径: str):
    # 初始化 API
    try:
        api = MainApi(debug=args.debug)
    except Exception as e:
        print(f"✗ 初始化失败：{e}")
        sys.exit(1)

    if not api.tokens.get("gitee"):
        print("✗ 未配置有效的 gitee token")
        print("  请用 `gmm config set gitee.token <token>` 配置")
        sys.exit(1)

    # 获取 gitee 用户名
    try:
        gitee用户名 = api.gitee_api.获取当前用户名()
    except Exception as e:
        print(f"✗ 获取 gitee 用户名失败：{e}")
        sys.exit(1)

    print(f"  Gitee 用户：{gitee用户名}")

    # 读取清单和缓存
    清单 = 模块清单(根仓库路径)
    缓存 = 处理缓存(根仓库路径)

    if 清单.数量() == 0:
        print("✗ 模块清单为空，请先添加模块")
        sys.exit(0)

    待处理 = 过滤待处理列表(清单, 缓存)
    print(f"  清单共 {清单.数量()} 个模块，本次待处理 {len(待处理)} 个")

    if not 待处理:
        print("\n✓ 无需处理的条目（全部已完成或跳过）")
        print("  使用 `gmm mark <url> --force-redo` 可强制重迁")
        sys.exit(0)

    # 决定实际执行模式
    是否dry_run = args.dry_run
    是否no_push = args.no_push
    模式说明 = "实际执行" if not 是否dry_run else "dry-run 模式"
    if 是否no_push:
        模式说明 = "no-push 模式（执行但不推送）"

    print(f"\n{'─' * 50}")
    print(f"  开始迁移（{模式说明}）")
    print(f"{'─' * 50}\n")

    # 缓存目录
    缓存仓库目录 = 解析缓存目录(api.config)

    # 白名单
    白名单域名 = 解析白名单域名(api.config)

    # 执行批量迁移
    结果 = 批量迁移(
        待处理列表=待处理,
        gitee_api=api.gitee_api,
        gitee用户名=gitee用户名,
        缓存根目录=缓存仓库目录,
        目标域名列表=["gitee.com"],
        白名单域名=白名单域名,
        处理缓存实例=缓存,
        dry_run=是否dry_run,
        no_push=是否no_push,
        logger=api.logger,
    )

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
        sys.exit(1)
    print(f"{'═' * 50}")

    # 迁移完成后自动应用到根仓库
    # 只有 dry_run 时不应用；no_push 也应用（只是不推送）
    if not 是否dry_run and 结果.状态 and 结果.数据 and 结果.数据.get("映射表"):
        print(f"\n{'─' * 50}")
        print(f"  应用到根仓库：{根仓库路径}")
        print(f"{'─' * 50}")
        _应用到根仓库(根仓库路径, 清单, 缓存, dry_run=False, no_push=是否no_push)


def _应用到根仓库(根仓库路径: str, 清单: 模块清单, 缓存: 处理缓存, dry_run=False, no_push=False):
    """
    遍历清单中每条 entry：
    1. 从缓存取最新映射 → 新 URL
    2. 检查根仓库现有子模块：
       - 按旧 URL 命中 → 删旧子模块 + 添新子模块（保留 name/path/branch）
       - 未命中 → 用清单中的 子模块名/路径/分支 新增子模块
    3. 全部完成后 commit（no_push 时跳过 push）
    """
    仓库 = Git工具(根仓库路径)
    子模块结果 = 仓库.获取子模块列表()
    现有子模块 = {}
    if 子模块结果.状态 and 子模块结果.数据:
        现有子模块 = {s["URL"]: s for s in 子模块结果.数据}

    映射 = 缓存.获取最新映射()

    for 条目 in 清单.模块列表:
        旧url = 条目["url"].strip().rstrip("/")
        新url = 映射.get(旧url)
        if not 新url:
            continue

        仓库名 = 旧url.split("/")[-1].removesuffix(".git")
        名称 = 条目.get("子模块名") or 仓库名
        路径 = 条目.get("子模块路径") or 仓库名
        分支 = 条目.get("追踪分支") or None

        if 旧url in 现有子模块:
            # 替换：删旧 + 添新
            旧信息 = 现有子模块[旧url]
            名称 = 旧信息["名称"]
            路径 = 旧信息["路径"]
            分支 = 旧信息.get("追踪分支") or 分支
            if not dry_run:
                仓库.删除子模块(名称)
                仓库.添加子模块(名称, 路径, 新url, 分支=分支)
            print(f"  替换子模块：{名称} → {新url}")
        else:
            # 新增
            if not dry_run:
                仓库.添加子模块(名称, 路径, 新url, 分支=分支)
            print(f"  新增子模块：{名称} @ {路径} → {新url}")

    # 提交（no_push 时跳过 push）
    if not dry_run:
        脏 = 仓库.是否有未提交更改()
        if 脏.状态 and 脏.数据:
            仓库.提交("[gmm] 同步子模块引用", 是否允许自动add=True)
            if no_push:
                print("  ✓ 已提交（--no-push，跳过推送）")
            else:
                for remote in 仓库.repo.remotes:
                    仓库.推送(远程名称=remote.name, 强制=True)
                print("  ✓ 已提交并推送")
        else:
            print("  - 无变更需要提交")


# ─────────────────────────────────────────────
# 子命令：gmm [name] list
# ─────────────────────────────────────────────
def cmd_list(args, 名称: str, 根仓库路径: str):
    清单 = 模块清单(根仓库路径)
    缓存 = 处理缓存(根仓库路径)

    print(f"\n{'═' * 50}")
    print(f"  根仓库：{名称 or 根仓库路径}")
    print(f"  清单：{清单.数量()} 个模块")
    print(f"{'─' * 50}")
    for 条目 in 清单.模块列表:
        url = 条目.get("url", "")
        已处理标记 = "✓" if 缓存.是否已处理(url) else "○"
        强制标记 = " !" if 缓存.强制重迁中(url) else ""
        print(f"  [{已处理标记}{强制标记}] {url}")
        新url = 缓存.获取新url(url) or ""
        if 新url:
            print(f"        → {新url}")

    print(f"\n{'─' * 50}")
    print(f"  缓存：{缓存.数量()} 条记录")
    print(f"{'═' * 50}")


# ─────────────────────────────────────────────
# 子命令：gmm [name] mark / unmark
# ─────────────────────────────────────────────
def cmd_mark(args, 名称: str, 根仓库路径: str):
    缓存 = 处理缓存(根仓库路径)
    for url in args.urls:
        if args.force_redo:
            缓存.设置标记(url, 强制重迁=True)
            print(f"  ? 已标记强制重迁：{url}")
        if args.skip_check:
            缓存.设置标记(url, 跳过本地校验=True)
            print(f"  ? 已标记跳过本地校验：{url}")


def cmd_unmark(args, 名称: str, 根仓库路径: str):
    缓存 = 处理缓存(根仓库路径)
    for url in args.urls:
        缓存.清除标记(url)
        print(f"  ✓ 已清除标记：{url}")


# ─────────────────────────────────────────────
# 子命令：gmm config
# ─────────────────────────────────────────────
def cmd_config_set(args):
    配置 = 加载用户配置()
    parts = args.key.split(".", 1)
    if len(parts) != 2:
        print("✗ 格式错误： section.key")
        print("  用法：gmm config set gitee.token <value>")
        sys.exit(1)
    section, key = parts
    配置.set(section, key, args.value)
    print(f"  ✓ 已设置 {section}.{key}")


def cmd_config_get(args):
    配置 = 加载用户配置()
    parts = args.key.split(".", 1)
    if len(parts) != 2:
        print("✗ 格式错误： section.key")
        sys.exit(1)
    section, key = parts
    try:
        value = 配置.get(section, key)
        print(value)
    except Exception as e:
        print(f"✗ 未找到：{args.key}")
        sys.exit(1)


# ─────────────────────────────────────────────
# 参数解析 & 主入口
# ─────────────────────────────────────────────
def main():
    argv = sys.argv[1:]
    名称, 剩余argv = _解析name和命令(argv)

    # ── 别名转换 ──
    if 剩余argv and 剩余argv[0] in 短命令别名:
        剩余argv[0] = 短命令别名[剩余argv[0]]

    # ── 帮助截获（--help-full） ──
    if "--help-full" in 剩余argv:
        print(get_full())
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog="gmm",
        description=get_brief(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    parser.add_argument("-h", "--help", action="store_true", help="显示帮助")

    subparsers = parser.add_subparsers(dest="command")

    # ── repo 子命令 ──
    repo_parser = subparsers.add_parser(
        "repo", help="根仓库注册管理",
        epilog=get_cmd("repo"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    repo_subparsers = repo_parser.add_subparsers(dest="repo_subcommand")

    repo_add = repo_subparsers.add_parser("add", help="注册根仓库")
    repo_add.add_argument("name", help="仓库名称")
    repo_add.add_argument("path", help="仓库路径")
    repo_add.add_argument("--备注", default="")

    repo_remove = repo_subparsers.add_parser("remove", help="删除注册")
    repo_remove.add_argument("name", help="仓库名称")

    repo_subparsers.add_parser("list", help="列出所有注册的根仓库")

    repo_default = repo_subparsers.add_parser("default", help="设置默认仓库")
    repo_default.add_argument("name", help="仓库名称")

    # ── config 子命令（别名 cfg） ──
    config_parser = subparsers.add_parser(
        "config", aliases=["cfg"], help="全局配置管理",
        epilog=get_cmd("config"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    config_subparsers = config_parser.add_subparsers(dest="config_subcommand")

    config_set = config_subparsers.add_parser("set", help="设置配置项")
    config_set.add_argument("key", help="配置项键，格式 section.key")
    config_set.add_argument("value", help="配置项值")

    config_get = config_subparsers.add_parser("get", help="读取配置项")
    config_get.add_argument("key", help="配置项键，格式 section.key")

    # ── add 子命令（需要根仓库） ──
    add_parser = subparsers.add_parser("add", help="添加仓库到迁移清单",
        epilog=get_cmd("add"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    add_parser.add_argument("urls", nargs="+", help="要添加的仓库 URL")
    add_parser.add_argument("--name", dest="name_arg", help="子模块名称（默认用仓库名）")
    add_parser.add_argument("--path", help="子模块路径（默认用仓库名）")
    add_parser.add_argument("--branch", help="追踪分支")

    # ── run 子命令（需要根仓库） ──
    run_parser = subparsers.add_parser("run", help="执行迁移",
        epilog=get_cmd("run"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    run_parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际执行")
    run_parser.add_argument("--no-push", "-np", action="store_true", help="执行迁移但不推送（用于本地测试，对应 dry_run）")


    # ── list 子命令（别名 ls） ──
    subparsers.add_parser("list", aliases=["ls"], help="查看迁移清单和状态",
        epilog=get_cmd("list"),
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # ── clean 子命令（需要根仓库） ──
    clean_parser = subparsers.add_parser("clean", help="清空根仓库所有子模块",
        epilog=get_cmd("clean"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    clean_parser.add_argument("--force", action="store_true", help="确认执行（必需）")

    # ── sync 子命令（需要根仓库） ──
    subparsers.add_parser("sync", help="从现有子模块导入清单",
        epilog=get_cmd("sync"),
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # ── mark / unmark 子命令（需要根仓库） ──
    mark_parser = subparsers.add_parser("mark", help="标记模块行为",
        epilog=get_cmd("mark"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mark_parser.add_argument("urls", nargs="+", help="要标记的 URL")
    mark_parser.add_argument("--force-redo", action="store_true", help="强制重新迁移")
    mark_parser.add_argument("--skip-check", action="store_true", help="跳过本地校验")

    unmark_parser = subparsers.add_parser("unmark", help="清除模块标记",
        epilog=get_cmd("unmark"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    unmark_parser.add_argument("urls", nargs="+", help="要清除标记的 URL")

    args = parser.parse_args(剩余argv)

    # ── 无命令 / --help / -h ──
    if not args.command or getattr(args, "help", False):
        if 名称:
            print(f"  识别到仓库：{名称}，但未指定命令")
        print(get_brief() if not args.command else get_full())
        sys.exit(0)

    # ── 分发命令 ──
    # repo / config 不需要根仓库
    if args.command == "repo":
        if not args.repo_subcommand:
            print(get_cmd("repo"))
            sys.exit(1)
        {
            "add":    cmd_repo_add,
            "remove": cmd_repo_remove,
            "list":   cmd_repo_list,
            "default": cmd_repo_default,
        }[args.repo_subcommand](args)
        return

    if args.command == "config":
        if not args.config_subcommand:
            print(get_cmd("config"))
            sys.exit(1)
        {
            "set": cmd_config_set,
            "get": cmd_config_get,
        }[args.config_subcommand](args)
        return

    # 其它命令需要定位根仓库
    仓库名称, 根仓库路径 = _定位(名称)

    {
        "add":    cmd_add,
        "run":    cmd_run,
        "list":   cmd_list,
        "clean":  cmd_clean,
        "sync":   cmd_sync,
        "mark":   cmd_mark,
        "unmark": cmd_unmark,
    }[args.command](args, 仓库名称, 根仓库路径)


if __name__ == "__main__":
    main()