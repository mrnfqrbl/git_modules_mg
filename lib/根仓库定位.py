"""
根仓库定位
==========
两种定位方式：
    1. 显式传入 name → 查 ~/.gmm/repos.json
    2. 未传 name → 从 cwd 向上找 .git 目录
       (找不到时再回退到注册表中标记的"默认"仓库)
"""
from __future__ import annotations

import os
from typing import Optional

from lib.根仓库注册 import 根仓库注册表


class 根仓库定位错误(Exception):
    pass


def 向上查找git仓库(起始目录: str) -> Optional[str]:
    """
    从起始目录向上逐级查找 `.git`，返回找到的根目录。
    `.git` 既可以是目录（普通仓库）也可以是文件（worktree/子模块）。
    """
    当前 = os.path.abspath(起始目录)
    上一个 = None
    while 当前 and 当前 != 上一个:
        git路径 = os.path.join(当前, ".git")
        if os.path.isdir(git路径) or os.path.isfile(git路径):
            return 当前
        上一个 = 当前
        当前 = os.path.dirname(当前)
    return None


def 定位根仓库(
    名称: Optional[str] = None,
    路径: Optional[str] = None,
    回退到默认: bool = True,
) -> tuple[str, str]:
    """
    返回 (使用的名称, 仓库绝对路径)。
    优先级：
        1. 显式 路径 参数（最高，常用于 --repo）
        2. 显式 名称 参数（查注册表）
        3. cwd 向上找 .git
        4. 注册表中的"默认"条目（仅当 回退到默认=True）

    找不到时抛 根仓库定位错误。
    """
    注册表 = 根仓库注册表()

    # 1. 显式路径
    if 路径:
        绝对路径 = os.path.abspath(路径)
        if not os.path.isdir(绝对路径):
            raise 根仓库定位错误(f"路径不存在或不是目录：{绝对路径}")
        if not (os.path.isdir(os.path.join(绝对路径, ".git"))
                or os.path.isfile(os.path.join(绝对路径, ".git"))):
            raise 根仓库定位错误(f"不是有效的 Git 仓库：{绝对路径}")
        # 反查 name
        反查名称 = ""
        for 名, 信息 in 注册表.仓库表.items():
            if os.path.abspath(信息.get("路径", "")) == 绝对路径:
                反查名称 = 名
                break
        return 反查名称, 绝对路径

    # 2. 显式 name
    if 名称:
        命中路径 = 注册表.获取(名称)
        if not 命中路径:
            raise 根仓库定位错误(
                f"未注册的根仓库名称：{名称}\n"
                f"可用 `gmm repo add <name> <path>` 注册，或 `gmm repo list` 查看。"
            )
        if not os.path.isdir(命中路径):
            raise 根仓库定位错误(f"注册的路径已不存在：{命中路径}")
        return 名称, 命中路径

    # 3. cwd 向上找 .git
    cwd_仓库 = 向上查找git仓库(os.getcwd())
    if cwd_仓库:
        # 反查 name
        反查名称 = ""
        for 名, 信息 in 注册表.仓库表.items():
            if os.path.abspath(信息.get("路径", "")) == cwd_仓库:
                反查名称 = 名
                break
        return 反查名称, cwd_仓库

    # 4. 默认
    if 回退到默认 and 注册表.默认名称:
        默认路径 = 注册表.获取(注册表.默认名称)
        if 默认路径 and os.path.isdir(默认路径):
            return 注册表.默认名称, 默认路径

    raise 根仓库定位错误(
        "无法定位根仓库：未指定 name、未指定 --repo、当前目录不在任何 git 仓库中、"
        "也没有注册默认仓库。\n"
        "可用 `gmm repo add <name> <path>` 先注册一个。"
    )
