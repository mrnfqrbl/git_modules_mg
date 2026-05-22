"""
缓存管理（v2）
==============
状态文件位置：<根仓库>/.sub_data/
    - submod.json       —— 待迁移清单（用户通过 add 维护）
    - submod_data.json  —— 已迁移记录（每条 URL 可有多条历史记录）

设计原则：
    - 状态跟着仓库走，工具本身不存项目状态
    - 单条 URL 可以保留多次迁移记录（按时间倒序），便于溯源
    - 子模块迁移记录"完整快照"：name / path / branch / 锁定的 commit
    - 不轻易删条目；通过"标记"控制跳过本地校验或强制重迁

submod.json 格式：
{
    "schema_version": 2,
    "模块列表": [
        {
            "url": "https://github.com/x/A.git",
            "子模块名":   "A",                 // 可选，缺省 = 仓库名
            "子模块路径": "submodules/A",      // 可选，缺省 = submodules/<仓库名>
            "追踪分支":   "main",              // 可选
            "添加时间":   "..."
        }
    ]
}

submod_data.json 格式（schema_version=2）：
{
    "schema_version": 2,
    "条目": {
        "https://github.com/x/A.git": {
            "标记": {                          // 影响下一次 run 行为
                "强制重迁":   false,
                "跳过本地校验": false
            },
            "记录": [                          // 倒序：[0] 是最新一次
                {
                    "新url":       "https://gitee.com/me/A.git",
                    "原始commit":   "abc...",
                    "迁移后commit": "def...",
                    "子模块快照": {              // 仅当作为子模块被处理过
                        "名称":     "A",
                        "路径":     "submodules/A",
                        "追踪分支": "main"
                    },
                    "处理时间": "..."
                }
            ]
        }
    }
}
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional


_SCHEMA_VERSION_清单 = 2
_SCHEMA_VERSION_缓存 = 2

子目录名 = ".sub_data"
清单文件名 = "submod.json"
缓存文件名 = "submod_data.json"


def 状态目录(根仓库路径: str) -> str:
    return os.path.join(根仓库路径, 子目录名)


def 清单路径(根仓库路径: str) -> str:
    return os.path.join(状态目录(根仓库路径), 清单文件名)


def 缓存路径(根仓库路径: str) -> str:
    return os.path.join(状态目录(根仓库路径), 缓存文件名)


def 规整url(url: str) -> str:
    return (url or "").strip().rstrip("/")


# ─────────────────────────────────────────────
# submod.json —— 待迁移清单
# ─────────────────────────────────────────────
class 模块清单:
    """根仓库下的待迁移清单"""

    def __init__(self, 根仓库路径: str):
        self.根仓库路径 = 根仓库路径
        self.文件路径 = 清单路径(根仓库路径)
        self._数据 = self._加载()

    def _加载(self) -> dict:
        if os.path.isfile(self.文件路径):
            try:
                with open(self.文件路径, "r", encoding="utf-8") as f:
                    数据 = json.load(f)
                    if not isinstance(数据, dict):
                        return self._空数据()
                    数据.setdefault("schema_version", _SCHEMA_VERSION_清单)
                    数据.setdefault("模块列表", [])
                    return 数据
            except (json.JSONDecodeError, OSError):
                pass
        return self._空数据()

    def _空数据(self) -> dict:
        return {"schema_version": _SCHEMA_VERSION_清单, "模块列表": []}

    def _保存(self):
        os.makedirs(os.path.dirname(self.文件路径), exist_ok=True)
        with open(self.文件路径, "w", encoding="utf-8") as f:
            json.dump(self._数据, f, ensure_ascii=False, indent=2)

    @property
    def 模块列表(self) -> list[dict]:
        return self._数据.setdefault("模块列表", [])

    def 获取所有url(self) -> list[str]:
        return [规整url(条目.get("url", "")) for 条目 in self.模块列表 if 条目.get("url")]

    def 查找(self, url: str) -> Optional[dict]:
        url = 规整url(url)
        for 条目 in self.模块列表:
            if 规整url(条目.get("url", "")) == url:
                return 条目
        return None

    def 添加模块(
        self,
        url: str,
        子模块名: Optional[str] = None,
        子模块路径: Optional[str] = None,
        追踪分支: Optional[str] = None,
    ) -> bool:
        """新增模块；已存在则更新可选字段并返回 False"""
        url = 规整url(url)
        if not url:
            return False

        现有 = self.查找(url)
        if 现有:
            改动 = False
            for 键, 值 in (("子模块名", 子模块名), ("子模块路径", 子模块路径), ("追踪分支", 追踪分支)):
                if 值 is not None and 现有.get(键) != 值:
                    现有[键] = 值
                    改动 = True
            if 改动:
                self._保存()
            return False

        条目 = {
            "url": url,
            "添加时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if 子模块名:
            条目["子模块名"] = 子模块名
        if 子模块路径:
            条目["子模块路径"] = 子模块路径
        if 追踪分支:
            条目["追踪分支"] = 追踪分支

        self.模块列表.append(条目)
        self._保存()
        return True

    def 删除模块(self, url: str) -> bool:
        url = 规整url(url)
        原长度 = len(self.模块列表)
        self._数据["模块列表"] = [
            条目 for 条目 in self.模块列表
            if 规整url(条目.get("url", "")) != url
        ]
        if len(self._数据["模块列表"]) < 原长度:
            self._保存()
            return True
        return False

    def 数量(self) -> int:
        return len(self.模块列表)


# ─────────────────────────────────────────────
# submod_data.json —— 多版本迁移记录
# ─────────────────────────────────────────────
_默认标记 = {"强制重迁": False, "跳过本地校验": False}


class 处理缓存:
    """根仓库下的迁移记录缓存"""

    def __init__(self, 根仓库路径: str):
        self.根仓库路径 = 根仓库路径
        self.文件路径 = 缓存路径(根仓库路径)
        self._数据 = self._加载()

    # ── IO ──
    def _加载(self) -> dict:
        if os.path.isfile(self.文件路径):
            try:
                with open(self.文件路径, "r", encoding="utf-8") as f:
                    数据 = json.load(f)
                if 数据.get("schema_version") == _SCHEMA_VERSION_缓存:
                    return 数据
                # 兼容旧 schema：尝试无损升级 v1 → v2
                if 数据.get("schema_version") == 1 and "已处理" in 数据:
                    return self._升级_v1_to_v2(数据)
            except (json.JSONDecodeError, OSError):
                pass
        return self._空数据()

    def _空数据(self) -> dict:
        return {"schema_version": _SCHEMA_VERSION_缓存, "条目": {}}

    def _升级_v1_to_v2(self, 旧数据: dict) -> dict:
        新数据 = self._空数据()
        for url, 信息 in 旧数据.get("已处理", {}).items():
            新数据["条目"][规整url(url)] = {
                "标记": dict(_默认标记),
                "记录": [{
                    "新url": 信息.get("新url", ""),
                    "原始commit": "",
                    "迁移后commit": "",
                    "子模块快照": None,
                    "处理时间": 信息.get("处理时间", ""),
                }],
            }
        return 新数据

    def _保存(self):
        os.makedirs(os.path.dirname(self.文件路径), exist_ok=True)
        with open(self.文件路径, "w", encoding="utf-8") as f:
            json.dump(self._数据, f, ensure_ascii=False, indent=2)

    # ── 内部 ──
    def _获取条目(self, url: str, 创建: bool = False) -> Optional[dict]:
        url = 规整url(url)
        条目表 = self._数据.setdefault("条目", {})
        if url in 条目表:
            return 条目表[url]
        if 创建:
            条目表[url] = {"标记": dict(_默认标记), "记录": []}
            return 条目表[url]
        return None

    # ── 查询 ──
    @property
    def 条目表(self) -> dict[str, dict]:
        return self._数据.setdefault("条目", {})

    def 是否已处理(self, url: str) -> bool:
        条目 = self._获取条目(url)
        return bool(条目 and 条目.get("记录"))

    def 最新记录(self, url: str) -> Optional[dict]:
        条目 = self._获取条目(url)
        if 条目 and 条目.get("记录"):
            return 条目["记录"][0]
        return None

    def 获取新url(self, url: str) -> Optional[str]:
        最新 = self.最新记录(url)
        return 最新.get("新url") if 最新 else None

    def 获取最新映射(self) -> dict[str, str]:
        """{旧url → 最新一次的新url}（每个 url 只取最新）"""
        映射 = {}
        for 旧url, 条目 in self.条目表.items():
            记录 = 条目.get("记录") or []
            if 记录 and 记录[0].get("新url"):
                映射[旧url] = 记录[0]["新url"]
        return 映射

    def 标记(self, url: str) -> dict:
        条目 = self._获取条目(url)
        if not 条目:
            return dict(_默认标记)
        return dict(_默认标记, **(条目.get("标记") or {}))

    def 强制重迁中(self, url: str) -> bool:
        return self.标记(url).get("强制重迁", False)

    def 跳过本地校验中(self, url: str) -> bool:
        return self.标记(url).get("跳过本地校验", False)

    def 数量(self) -> int:
        return len(self.条目表)

    # ── 写入 ──
    def 追加记录(
        self,
        旧url: str,
        新url: str,
        原始commit: str = "",
        迁移后commit: str = "",
        子模块快照: Optional[dict] = None,
    ):
        """在条目顶部插入一条新记录（最新优先）"""
        条目 = self._获取条目(旧url, 创建=True)
        条目.setdefault("记录", []).insert(0, {
            "新url": 新url,
            "原始commit": 原始commit or "",
            "迁移后commit": 迁移后commit or "",
            "子模块快照": 子模块快照,  # None 或 {"名称","路径","追踪分支"}
            "处理时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._保存()

    def 设置标记(self, url: str, **标记):
        """更新某 url 的标记位（强制重迁 / 跳过本地校验）"""
        条目 = self._获取条目(url, 创建=True)
        当前 = 条目.setdefault("标记", dict(_默认标记))
        for 键, 值 in 标记.items():
            if 键 in _默认标记:
                当前[键] = bool(值)
        self._保存()

    def 清除标记(self, url: str, *标记键):
        条目 = self._获取条目(url)
        if not 条目:
            return
        当前 = 条目.setdefault("标记", dict(_默认标记))
        if not 标记键:
            for 键 in list(_默认标记.keys()):
                当前[键] = False
        else:
            for 键 in 标记键:
                if 键 in 当前:
                    当前[键] = False
        self._保存()

    def 删除条目(self, url: str) -> bool:
        url = 规整url(url)
        if url in self.条目表:
            del self.条目表[url]
            self._保存()
            return True
        return False

    def 清空(self):
        self._数据["条目"] = {}
        self._保存()


# ─────────────────────────────────────────────
# 过滤逻辑
# ─────────────────────────────────────────────
def 过滤待处理列表(清单: 模块清单, 缓存: 处理缓存) -> list[str]:
    """
    返回需要本次处理的 URL 列表。
    规则：
        - 未在缓存中 → 处理
        - 标记为"强制重迁" → 处理
        - 否则跳过
    """
    待处理 = []
    for url in 清单.获取所有url():
        if 缓存.强制重迁中(url):
            待处理.append(url)
            continue
        if not 缓存.是否已处理(url):
            待处理.append(url)
    return 待处理
