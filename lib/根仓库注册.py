"""
根仓库注册表
============
位置：~/.gmm/repos.json
作用：维护 name → 本地路径 的映射，让用户可以用 `gmm <name> <cmd>` 在
      任意目录下管理某个根仓库。

格式：
{
    "schema_version": 1,
    "默认": "ComfyUI",                # 可选，未指定 name 且不在仓库目录时回退到此
    "仓库": {
        "ComfyUI": {
            "路径": "D:/xm/ComfyUI",
            "注册时间": "2025-01-01 12:00:00",
            "备注": ""
        }
    }
}
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from lib.用户配置 import 用户根目录


_SCHEMA_VERSION = 1


def 注册表路径() -> str:
    return os.path.join(用户根目录(), "repos.json")


class 根仓库注册表:
    """对 ~/.gmm/repos.json 的薄封装"""

    def __init__(self):
        self.路径 = 注册表路径()
        self._数据 = self._加载()

    # ── IO ──────────────────────────────────────────────
    def _加载(self) -> dict:
        if os.path.isfile(self.路径):
            try:
                with open(self.路径, "r", encoding="utf-8") as f:
                    数据 = json.load(f)
                if 数据.get("schema_version") != _SCHEMA_VERSION:
                    return self._空数据()
                return 数据
            except (json.JSONDecodeError, OSError):
                return self._空数据()
        return self._空数据()

    def _空数据(self) -> dict:
        return {"schema_version": _SCHEMA_VERSION, "默认": "", "仓库": {}}

    def _保存(self):
        os.makedirs(os.path.dirname(self.路径), exist_ok=True)
        with open(self.路径, "w", encoding="utf-8") as f:
            json.dump(self._数据, f, ensure_ascii=False, indent=2)

    # ── 查询 ────────────────────────────────────────────
    @property
    def 仓库表(self) -> dict[str, dict]:
        return self._数据.setdefault("仓库", {})

    @property
    def 默认名称(self) -> str:
        return self._数据.get("默认", "") or ""

    def 获取(self, 名称: str) -> Optional[str]:
        条目 = self.仓库表.get(名称)
        if not 条目:
            return None
        return 条目.get("路径") or None

    def 列出(self) -> list[tuple[str, str]]:
        return [(名称, 信息.get("路径", "")) for 名称, 信息 in self.仓库表.items()]

    # ── 写入 ────────────────────────────────────────────
    def 注册(self, 名称: str, 路径: str, 备注: str = "") -> bool:
        """
        登记或更新一个根仓库。
        路径不存在或不是 git 仓库时返回 False；成功返回 True。
        """
        if not 名称 or not 名称.strip():
            return False
        路径 = os.path.abspath(路径)
        # 问题: 强制要求 .git 为目录，导致 submodule 或 worktree (其 .git 为文件) 无法注册
        if not os.path.isdir(路径) or not os.path.isdir(os.path.join(路径, ".git")):
            return False

        self.仓库表[名称] = {
            "路径": 路径,
            "备注": 备注,
            "注册时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if not self.默认名称:
            self._数据["默认"] = 名称
        self._保存()
        return True

    def 删除(self, 名称: str) -> bool:
        if 名称 in self.仓库表:
            del self.仓库表[名称]
            if self.默认名称 == 名称:
                self._数据["默认"] = next(iter(self.仓库表.keys()), "")
            self._保存()
            return True
        return False

    def 设默认(self, 名称: str) -> bool:
        if 名称 in self.仓库表:
            self._数据["默认"] = 名称
            self._保存()
            return True
        return False
