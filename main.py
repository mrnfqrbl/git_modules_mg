#!/usr/bin/env python3
"""gmm - Git Modules Manager 全局 CLI"""
from __future__ import annotations

import argparse
import os
import sys
import git

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

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

所有命令名集合 = set(短命令别名.keys()) | set(短命令别名.values()) | {"--help-full", "ir", "get"}


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

    # 提取根仓库的子模块锁定信息，以支持子模块指针变更时的自动增量更新
    from lib.git_command import Git工具
    from lib.缓存管理 import 规整url
    子模块锁定表 = {}
    try:
        子模块结果 = Git工具(根仓库路径).获取子模块列表()
        if 子模块结果.状态 and 子模块结果.数据:
            for item in 子模块结果.数据:
                sub_url = item.get("URL") or item.get("url")
                if sub_url:
                    子模块锁定表[规整url(sub_url)] = item.get("锁定的提交哈希")
    except Exception as ge:
        api.logger.warning(f"获取根仓库子模块锁定信息失败：{ge}")

    待处理 = 过滤待处理列表(清单, 缓存, 子模块锁定表)
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
    is_public = bool(args.public)
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
        public=is_public,
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
            
            # 记录 Gitee URLs
            gitee_urls = sorted(list(set([val for val in 数据["映射表"].values() if val])))
            urls_file = os.path.join(根仓库路径, ".sub_data", "gitee_urls.txt")
            try:
                os.makedirs(os.path.dirname(urls_file), exist_ok=True)
                with open(urls_file, "w", encoding="utf-8") as f:
                    for url in gitee_urls:
                        f.write(url + "\n")
                if gitee_urls:
                    print(f"\n  ✓ 已记录所有迁移的 Gitee 仓库 URL 至: {urls_file}")
            except Exception as e:
                print(f"\n  ⚠ 记录 Gitee URL 失败: {str(e)}")
    else:
        print(f"  迁移结果：{结果.错误信息}")
        sys.exit(1)
    print(f"{'═' * 50}")

    # 迁移完成后自动应用到根仓库
    # 只有 dry_run 时不应用；no_push 也应用（只是不推送）
    if not 是否dry_run and 结果.状态 and 结果.数据:
        print(f"\n{'─' * 50}")
        print(f"  应用到根仓库：{根仓库路径}")
        print(f"{'─' * 50}")
        _应用到根仓库(根仓库路径, 清单, 缓存, dry_run=False, no_push=是否no_push)


def _应用到根仓库(根仓库路径: str, 清单: 模块清单, 缓存: 处理缓存, dry_run=False, no_push=False):
    """
    遍历清单中每条 entry：
    1. 从缓存取最新映射 → 新 URL
    2. 检查根仓库现有子模块：
       - 按 名称、路径 或 旧/新 URL 命中 → 替换子模块（先删旧，再添新，保留原有属性，并精确检出对应 commit 指针）
       - 未命中 → 用清单中的 子模块名/路径/分支 新增子模块（同样精确检出对应 commit 指针）
    3. 全部完成后 commit（no_push 时跳过 push）
    """
    仓库 = Git工具(根仓库路径)
    子模块结果 = 仓库.获取子模块列表()
    
    # 建立多索引的现有子模块字典，防止因 URL 已经被改写为 Gitee 而匹配失败
    现有子模块 = {}          # 按 URL
    现有子模块_按名称 = {}    # 按名称
    现有子模块_按路径 = {}    # 按路径
    
    if 子模块结果.状态 and 子模块结果.数据:
        for s in 子模块结果.数据:
            现有子模块[s["URL"]] = s
            现有子模块_按名称[s["名称"]] = s
            现有子模块_按路径[s["路径"]] = s

    白名单 = 解析白名单域名()
    映射 = 缓存.获取最新映射()

    for 条目 in 清单.模块列表:
        旧url = 条目["url"].strip().rstrip("/")
        新url = 映射.get(旧url)
        if not 新url:
            # 检查是否因为是白名单域名而被跳过。如果是，则直接将旧url作为新url使用
            is_whitelist = False
            for 域名 in 白名单:
                if 域名 in 旧url:
                    is_whitelist = True
                    break
            if is_whitelist:
                新url = 旧url
            else:
                continue

        仓库名 = 旧url.split("/")[-1].removesuffix(".git")
        默认名称 = 条目.get("子模块名") or 仓库名
        默认路径 = 条目.get("子模块路径") or 仓库名
        分支 = 条目.get("追踪分支") or None

        # 只要名称、路径或 URL 匹配，就说明该子模块已经存在于根仓库
        现有 = 现有子模块_按名称.get(默认名称) or 现有子模块_按路径.get(默认路径) or 现有子模块.get(旧url)

        # 获取需要检出的正确 commit
        最新 = 缓存.最新记录(旧url)
        目标commit = 最新.get("迁移后commit") if 最新 else None

        is_whitelist = False
        for 域名 in 白名单:
            if 域名 in 旧url:
                is_whitelist = True
                break

        if is_whitelist and 现有:
            # 如果是白名单域名（已在目标平台），则对比本地和远程内容。目前只针对迁移前原 URL 属于 mrnfqrbl 的个人仓库运行自动更新。
            is_personal = "mrnfqrbl" in 旧url.lower()
            if is_personal:
                sub_path = os.path.join(根仓库路径, 现有["路径"])
                if os.path.isdir(os.path.join(sub_path, ".git")) or os.path.isfile(os.path.join(sub_path, ".git")):
                    try:
                        sub_repo = git.Repo(sub_path)
                        branch_name = 现有.get("追踪分支") or 条目.get("追踪分支")
                        remote_commit = get_remote_latest_commit(sub_repo, branch_name)
                        if remote_commit:
                            local_commit = sub_repo.head.commit.hexsha
                            if local_commit != remote_commit:
                                if sub_repo.is_ancestor(local_commit, remote_commit):
                                    print(f"  子模块 {现有['名称']} 本地提交落后于远程 ({local_commit[:8]} -> {remote_commit[:8]})，将执行更新...")
                                    目标commit = remote_commit
                                else:
                                    print(f"  子模块 {现有['名称']} 本地提交与远程不一致，但本地未落后，跳过自动更新")
                    except Exception as e:
                        print(f"  ⚠ 比较子模块 {现有['名称']} 本地和远程失败: {str(e)}")

        if not 目标commit and 现有:
            目标commit = 现有.get("锁定的提交哈希")

        if 现有:
            名称 = 现有["名称"]
            路径 = 现有["路径"]
            分支 = 现有.get("追踪分支") or 分支
            
            if 现有["URL"] == 新url:
                if submodule_at_commit(仓库.repo, 名称, 目标commit):
                    print(f"  子模块 {名称} 已是最新的（URL与提交哈希均匹配）：{新url}")
                    continue
                else:
                    if not dry_run:
                        print(f"  更新已有的子模块指针：{名称} → {目标commit[:8] if 目标commit else 'latest'}")
                        if 目标commit:
                            checkout_submodule_to_commit(仓库.repo, 名称, 路径, 目标commit)
                    continue

            if not dry_run:
                # 删除旧子模块
                删结果 = 仓库.删除子模块(名称)
                if not 删结果.状态:
                    raise RuntimeError(f"应用时删除旧子模块 {名称} 失败：{删结果.错误信息}")
                # 添加新子模块
                添结果 = 仓库.添加子模块(名称, 路径, 新url, 分支=分支)
                if not 添结果.状态:
                    raise RuntimeError(f"应用时添加新子模块 {名称} 失败：{添结果.错误信息}")
                # 精确检出对应的 commit 指针
                if 目标commit:
                    checkout_submodule_to_commit(仓库.repo, 名称, 路径, 目标commit)
            print(f"  替换子模块：{名称} → {新url}")
        else:
            # 新增
            if not dry_run:
                添结果 = 仓库.添加子模块(默认名称, 默认路径, 新url, 分支=分支)
                if not 添结果.状态:
                    raise RuntimeError(f"应用时新增子模块 {默认名称} 失败：{添结果.错误信息}")
                # 精确检出对应的 commit 指针
                if 目标commit:
                    checkout_submodule_to_commit(仓库.repo, 默认名称, 默认路径, 目标commit)
            print(f"  新增子模块：{默认名称} @ {默认路径} → {新url}")

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


def get_remote_latest_commit(sub_repo, branch_name: str = None) -> str | None:
    """获取子模块远程的最新 commit hash"""
    try:
        sub_repo.git.fetch("origin")
        if not branch_name:
            try:
                ref = sub_repo.git.symbolic_ref("refs/remotes/origin/HEAD")
                branch_name = ref.split("/")[-1]
            except Exception:
                for b in ["main", "master", "develop"]:
                    try:
                        sub_repo.commit(f"origin/{b}")
                        branch_name = b
                        break
                    except Exception:
                        pass
        
        if branch_name:
            commit_sha = sub_repo.commit(f"origin/{branch_name}").hexsha
            return commit_sha
    except Exception as e:
        print(f"  ⚠ 获取子模块远程最新提交失败: {str(e)}")
    return None


def submodule_at_commit(parent_repo, name: str, commit: str) -> bool:
    """检查子模块是否已经在正确的 commit 上"""
    if not commit:
        return True
    try:
        sub = parent_repo.submodule(name)
        return sub.hexsha == commit
    except Exception:
        return False


def checkout_submodule_to_commit(parent_repo, name: str, path: str, commit: str):
    """更新子模块并将其 checkout 到指定的 commit，随后 add 路径"""
    try:
        # 1. 尝试直接通过本地路径打开子仓库对象（最稳妥，避开 GitPython 内部对 submodule 列表的缓存/中文路径 Bug）
        sub_repo_path = os.path.join(parent_repo.working_tree_dir, path)
        sub_repo = None
        if os.path.exists(os.path.join(sub_repo_path, ".git")):
            try:
                sub_repo = git.Repo(sub_repo_path)
            except Exception:
                pass
        
        # 2. 如果直接打开失败，尝试退回到标准的 GitPython 子模块对象获取
        if not sub_repo:
            if hasattr(parent_repo, "_submodules"):
                try:
                    del parent_repo._submodules
                except Exception:
                    pass
            sub = parent_repo.submodule(name)
            sub.update(init=True, force=True)
            sub_repo = sub.module()

        # 3. 确保本地已拉取最新的 commit
        try:
            sub_repo.git.fetch()
        except Exception:
            pass
        sub_repo.git.checkout(commit, force=True)
        try:
            from lib.util import 解除gitignore限制
            解除gitignore限制(parent_repo, path)
        except Exception:
            pass
        parent_repo.git.add("-f", path)
    except Exception as e:
        print(f"  ⚠ 检出子模块 {name} 到 {commit[:8]} 失败: {str(e)}")


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


def cmd_ir(args, 名称: str, 根仓库路径: str):
    import subprocess
    import sys
    from lib.git_command import Git工具

    print(f"\n{'═' * 50}")
    print(f"  开始递归安装依赖：{名称 or 根仓库路径}")
    print(f"{'═' * 50}\n")

    def 获取所有递归子仓库(当前路径: str) -> list[str]:
        结果 = []
        try:
            子模块结果 = Git工具(当前路径).获取子模块列表()
            if 子模块结果.状态 and 子模块结果.数据:
                for 子模块 in 子模块结果.数据:
                    子路径 = os.path.join(当前路径, 子模块["路径"])
                    if os.path.isdir(子路径):
                        结果.append(子路径)
                        结果.extend(获取所有递归子仓库(子路径))
        except Exception:
            pass
        return 结果

    # 仅安装递归子仓库依赖，不包含根仓库自身
    仓库列表 = 获取所有递归子仓库(根仓库路径)
    python_exe = args.python_exe or sys.executable

    if not 仓库列表:
        print(f"  - 未发现任何子仓库")
    else:
        for i, 仓库路径 in enumerate(仓库列表, 1):
            相对路径 = os.path.relpath(仓库路径, 根仓库路径)
            显示名称 = 相对路径
            print(f"[{i}/{len(仓库列表)}] 正在处理子仓库: {显示名称}")

            # 查找依赖文件
            has_requirements = os.path.isfile(os.path.join(仓库路径, "requirements.txt"))
            has_setup = os.path.isfile(os.path.join(仓库路径, "setup.py"))
            has_pyproject = os.path.isfile(os.path.join(仓库路径, "pyproject.toml"))

            if not (has_requirements or has_setup or has_pyproject):
                print(f"  - 跳过（未发现 Python 依赖文件）")
                continue

            failed = False

            if has_requirements:
                print(f"  - 发现 requirements.txt, 正在执行安装...")
                cmd = [python_exe, "-m", "pip", "install", "-r", "requirements.txt"]
                try:
                    subprocess.run(cmd, cwd=仓库路径, check=True)
                    print(f"    ✓ requirements.txt 安装成功")
                except Exception as e:
                    # 问题: 未捕获 OSError (如 FileNotFoundError)，若解释器路径不存在会导致程序崩溃
                    print(f"    ✗ requirements.txt 安装失败: {e}")
                    err_msg = str(e)
                    if "WinError 5" in err_msg or "拒绝访问" in err_msg or "PermissionError" in err_msg:
                        print("      [提示] 遇到 WinError 5 拒绝访问错误。请检查是否有 ComfyUI 或其他 Python 后台进程正在运行并占用了该虚拟环境，如有请先关闭它们再重试。")
                    failed = True

            if (has_setup or has_pyproject):
                if not args.editable:
                    print(f"  - 发现 setup.py/pyproject.toml, 默认跳过可编辑安装 (使用 -e/--editable 开启)")
                else:
                    file_name = "setup.py" if has_setup else "pyproject.toml"
                    print(f"  - 发现 {file_name}, 正在执行可编辑安装...")
                    cmd = [python_exe, "-m", "pip", "install", "-e", "."]
                    try:
                        subprocess.run(cmd, cwd=仓库路径, check=True)
                        print(f"    ✓ {file_name} 可编辑安装成功")
                    except Exception as e:
                        # 问题: 未捕获 OSError (如 FileNotFoundError)，若解释器路径不存在会导致程序崩溃
                        print(f"    ✗ {file_name} 可编辑安装失败: {e}")
                        err_msg = str(e)
                        if "WinError 5" in err_msg or "拒绝访问" in err_msg or "PermissionError" in err_msg:
                            print("      [提示] 遇到 WinError 5 拒绝访问错误。请检查是否有 ComfyUI 或其他 Python 后台进程正在运行并占用了该虚拟环境，如有请先关闭它们再重试。")
                        failed = True

            if failed and not args.ignore_errors:
                print(f"\n✗ 依赖安装失败，正在中止执行。可以使用 --ignore-errors (-ie) 忽略错误继续处理其他仓库。")
                sys.exit(1)

    print(f"\n{'═' * 50}")
    print(f"  所有子仓库依赖安装处理完成")
    print(f"{'═' * 50}\n")


def cmd_get(args, 名称: str, 根仓库路径: str):
    if not args.get_subcommand:
        print(get_cmd("get"))
        sys.exit(1)
    if args.get_subcommand == "info":
        cmd_get_info(args, 名称, 根仓库路径)


def cmd_get_info(args, 名称: str, 根仓库路径: str):
    from lib.引用载体适配器 import GitModules适配器, 收集所有依赖

    print(f"\n{'═' * 50}")
    print(f"  根仓库依赖树：{名称 or 根仓库路径}")
    print(f"{'═' * 50}\n")

    根显示 = 名称 or os.path.basename(根仓库路径)
    print(f"📁 {根显示}")

    visited = set()

    def 获取子仓库依赖(路径: str, 深度: int) -> list[dict]:
        deps = []
        if 深度 == 0:
            adapter = GitModules适配器()
            if adapter.识别(路径):
                try:
                    for dep in adapter.解析(路径):
                        deps.append({
                            "type": "子模块",
                            "name": dep.仓库名,
                            "url": dep.url,
                            "path": dep.路径,
                            "source": ".gitmodules"
                        })
                except Exception:
                    pass
        else:
            # 1. 扫描本体文件依赖
            native_deps = []
            try:
                raw_deps = 收集所有依赖(路径)
                for dep in raw_deps:
                    if dep.引用类型 == "子模块":
                        native_deps.append({
                            "type": "子模块",
                            "name": dep.仓库名,
                            "url": dep.url,
                            "path": dep.路径,
                            "source": dep.载体文件
                        })
                    else:
                        native_deps.append({
                            "type": "pip依赖",
                            "name": dep.仓库名,
                            "url": dep.url,
                            "source": dep.载体文件
                        })
            except Exception:
                pass

            # 2. 读取 .gmm_map.json 数据
            json_deps = []
            gmm_map_path = os.path.join(路径, ".gmm_map.json")
            if os.path.isfile(gmm_map_path):
                import json
                try:
                    with open(gmm_map_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for item in data.get("子依赖列表", []):
                            item_path = item.get("路径", "")
                            item_name = item.get("名称", "")
                            item_url = item.get("原始url", "")
                            item_new_url = item.get("新url", "")
                            is_pip = item_path.replace("\\", "/").startswith("submodules/")
                            json_deps.append({
                                "type": "pip依赖" if is_pip else "子模块",
                                "name": item_name,
                                "url": item_url,
                                "new_url": item_new_url,
                                "path": item_path,
                                "source": ".gmm_map.json"
                            })
                except Exception:
                    pass

            # 3. 综合合并：融合 native_deps 和 json_deps
            def clean_url(u):
                if not u: return ""
                return u.strip().rstrip("/").removesuffix(".git").lower()

            matched_json_indices = set()
            for nd in native_deps:
                matched_item = None
                for idx, jd in enumerate(json_deps):
                    if idx in matched_json_indices:
                        continue
                    
                    url_match = (clean_url(nd["url"]) == clean_url(jd["url"]))
                    name_path_match = False
                    if nd["type"] == "子模块" and jd["type"] == "子模块":
                        name_path_match = (nd["path"] == jd["path"] or nd["name"] == jd["name"])
                    
                    if url_match or name_path_match:
                        matched_item = jd
                        matched_json_indices.add(idx)
                        break
                
                if matched_item:
                    merged_source = f"{nd['source']} + .gmm_map.json"
                    deps.append({
                        "type": nd["type"],
                        "name": nd["name"],
                        "url": nd["url"],
                        "new_url": matched_item.get("new_url"),
                        "path": nd.get("path") or matched_item.get("path"),
                        "source": merged_source
                    })
                else:
                    deps.append(nd)

            # 将 json 中有但本地代码中未发现的额外依赖也合并进来
            for idx, jd in enumerate(json_deps):
                if idx not in matched_json_indices:
                    deps.append(jd)

        return deps

    def build_tree(当前路径: str, 深度: int = 0, 前缀: str = ""):
        依赖列表 = 获取子仓库依赖(当前路径, 深度)
        总数 = len(依赖列表)
        
        for i, dep in enumerate(依赖列表):
            is_last = (i == 总数 - 1)
            connector = "└── " if is_last else "├── "
            next_prefix = 前缀 + ("    " if is_last else "│   ")
            
            if dep["type"] == "子模块":
                子绝对路径 = os.path.join(当前路径, dep["path"])
                exists = os.path.isdir(os.path.join(子绝对路径, ".git")) or os.path.isfile(os.path.join(子绝对路径, ".git"))
                status_str = "" if exists else " (未初始化)"
                
                url_str = ""
                if dep.get("new_url"):
                    url_str = f" [URL: {dep['url']} ➔ {dep['new_url']}]"
                else:
                    url_str = f" [URL: {dep['url']}]"
                    
                print(f"{前缀}{connector}📦 {dep['name']}{status_str} [路径: {dep['path']}]{url_str}")
                
                clean_url = dep["url"].rstrip("/").removesuffix(".git")
                if clean_url in visited:
                    print(f"{next_prefix}└── 🔁 (循环引用/已访问: {dep['url']})")
                elif exists:
                    visited.add(clean_url)
                    build_tree(子绝对路径, 深度 + 1, next_prefix)
            else:
                display_url = dep["url"]
                if not display_url.startswith("git+"):
                    display_url = "git+" + display_url
                new_display_url = dep.get("new_url")
                if new_display_url:
                    if not new_display_url.startswith("git+"):
                        new_display_url = "git+" + new_display_url
                    print(f"{前缀}{connector}🐍 {dep['name']} [来源: {dep['source']}]")
                    print(f"{next_prefix}└─ URL: {display_url} ➔ {new_display_url}")
                else:
                    print(f"{前缀}{connector}🐍 {dep['name']} [来源: {dep['source']}]")
                    print(f"{next_prefix}└─ URL: {display_url}")

    build_tree(根仓库路径, 0, "")
    print(f"\n{'═' * 50}\n")


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
    add_parser.add_argument("--name", "-n", dest="name_arg", help="子模块名称（默认用仓库名）")
    add_parser.add_argument("--path", "-p", help="子模块路径（默认用仓库名）")
    add_parser.add_argument("--branch", "-b", help="追踪分支")

    # ── run 子命令（需要根仓库） ──
    run_parser = subparsers.add_parser("run", help="执行迁移",
        epilog=get_cmd("run"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    run_parser.add_argument("--dry-run", "-dr", action="store_true", help="预览模式，不实际执行")
    run_parser.add_argument("--no-push", "-np", action="store_true", help="执行迁移但不推送（用于本地测试，对应 dry_run）")
    run_parser.add_argument("--public", "-pb", type=int, choices=[0, 1], nargs="?", const=1, default=1, help="是否公开仓库 (0: 私有, 1: 公开)，默认为 1")


    # ── list 子命令（别名 ls） ──
    subparsers.add_parser("list", aliases=["ls"], help="查看迁移清单和状态",
        epilog=get_cmd("list"),
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # ── clean 子命令（需要根仓库） ──
    clean_parser = subparsers.add_parser("clean", help="清空根仓库所有子模块",
        epilog=get_cmd("clean"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    clean_parser.add_argument("--force", "-f", action="store_true", help="确认执行（必需）")

    # ── sync 子命令（需要根仓库） ──
    subparsers.add_parser("sync", help="从现有子模块导入清单",
        epilog=get_cmd("sync"),
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # ── mark / unmark 子命令（需要根仓库） ──
    mark_parser = subparsers.add_parser("mark", aliases=["m"], help="标记模块行为",
        epilog=get_cmd("mark"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mark_parser.add_argument("urls", nargs="+", help="要标记的 URL")
    mark_parser.add_argument("--force-redo", "-fr", "-f", action="store_true", help="强制重新迁移")
    mark_parser.add_argument("--skip-check", "-skip", "-s", action="store_true", help="跳过本地校验")

    unmark_parser = subparsers.add_parser("unmark", aliases=["um"], help="清除模块标记",
        epilog=get_cmd("unmark"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    unmark_parser.add_argument("urls", nargs="+", help="要清除标记的 URL")

    # ── ir 子命令（需要根仓库） ──
    ir_parser = subparsers.add_parser("ir", help="递归安装所有子仓库的依赖文件和setup.py和toml等",
        epilog=get_cmd("ir"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ir_parser.add_argument("--python","-p", dest="python_exe", default=None, help="指定用于安装依赖的 Python 解释器路径")
    ir_parser.add_argument("--editable", "-e", action="store_true", help="执行 setup.py 和 pyproject.toml 的可编辑安装 (pip install -e .)")
    ir_parser.add_argument("--ignore-errors", "-ie", action="store_true", help="忽略单个子仓库的安装错误，继续处理其它仓库")

    # ── get 子命令（需要根仓库） ──
    get_parser = subparsers.add_parser("get", help="获取仓库依赖树信息",
        epilog=get_cmd("get"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    get_subparsers = get_parser.add_subparsers(dest="get_subcommand")
    get_subparsers.add_parser("info", help="输出根仓库下所有递归子仓库/依赖以树形")

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
        "ir":     cmd_ir,
        "get":    cmd_get,
    }[args.command](args, 仓库名称, 根仓库路径)


if __name__ == "__main__":
    main()