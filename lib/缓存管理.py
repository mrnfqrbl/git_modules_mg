"""
缓存管理模块
============
维护两个 JSON 文件（位于根仓库目录下）：

1. submod.json —— 待迁移模块清单（用户通过 命令行 add 添加）
   格式：
   {
       "模块列表": [
           {"url": "https://github.com/xxx/yyy.git", "添加时间": "..."},
           ...
       ]
   }

2. submod_data.json —— 已处理缓存（用于跳过已迁移过的条目）
   格式：
   {
       "schema_version": 1,
       "已处理": {
           "https://github.com/xxx/yyy.git": {
               "新url": "https://gitee.com/user/yyy.git",
               "处理时间": "2025-01-01 12:00:00",
               "仓库名": "yyy"
           },
           ...
       }
   }

设计原则：
    - 见过的跳过，没见过的处理
    - --refresh 插件名 从已处理中删除对应条目 → 下次 run 时重新处理
    - 不存过期时间、不存 DAG、不存依赖树
    - JSON 扁平、人眼可读、出问题能手改
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────
# submod.json 管理（待迁移清单）
# ─────────────────────────────────────────────
class 模块清单:
    """管理 submod.json —— 用户维护的"我要迁移哪些模块"清单"""

    def __init__(self, 文件路径: str):
        self.文件路径 = 文件路径
        self._数据 = self._加载()

    def _加载(self) -> dict:
        if os.path.isfile(self.文件路径):
            with open(self.文件路径, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {"模块列表": []}
        return {"模块列表": []}

    def _保存(self):
        os.makedirs(os.path.dirname(self.文件路径) or ".", exist_ok=True)
        with open(self.文件路径, "w", encoding="utf-8") as f:
            json.dump(self._数据, f, ensure_ascii=False, indent=2)

    @property
    def 模块列表(self) -> list[dict]:
        return self._数据.get("模块列表", [])

    def 获取所有url(self) -> list[str]:
        """返回清单中所有模块的 URL 列表"""
        return [条目["url"] for 条目 in self.模块列表 if "url" in 条目]

    def 添加模块(self, url: str) -> bool:
        """
        添加一个模块到清单。
        如果已存在则跳过，返回 False；新增返回 True。
        """
        url = url.strip().rstrip("/")
        # 去重
        已有 = {条目["url"].rstrip("/") for 条目 in self.模块列表}
        if url in 已有:
            return False

        self._数据.setdefault("模块列表", []).append({
            "url": url,
            "添加时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._保存()
        return True

    def 删除模块(self, url: str) -> bool:
        """从清单中移除指定 URL 的模块"""
        url = url.strip().rstrip("/")
        原长度 = len(self.模块列表)
        self._数据["模块列表"] = [
            条目 for 条目 in self.模块列表
            if 条目.get("url", "").rstrip("/") != url
        ]
        if len(self._数据["模块列表"]) < 原长度:
            self._保存()
            return True
        return False

    def 是否包含(self, url: str) -> bool:
        url = url.strip().rstrip("/")
        return url in {条目["url"].rstrip("/") for 条目 in self.模块列表}

    def 数量(self) -> int:
        return len(self.模块列表)


# ─────────────────────────────────────────────
# submod_data.json 管理（已处理缓存）
# ─────────────────────────────────────────────
_SCHEMA_VERSION = 1


class 处理缓存:
    """
    管理 submod_data.json —— 记录"哪些模块已经成功迁移过"。
    用于跳过已处理的条目，避免重复 API 调用和克隆。
    """

    def __init__(self, 文件路径: str):
        self.文件路径 = 文件路径
        self._数据 = self._加载()

    def _加载(self) -> dict:
        if os.path.isfile(self.文件路径):
            with open(self.文件路径, "r", encoding="utf-8") as f:
                try:
                    数据 = json.load(f)
                    # 版本兼容：如果格式不对就重建
                    if 数据.get("schema_version") != _SCHEMA_VERSION:
                        return {"schema_version": _SCHEMA_VERSION, "已处理": {}}
                    return 数据
                except json.JSONDecodeError:
                    pass
        return {"schema_version": _SCHEMA_VERSION, "已处理": {}}

    def _保存(self):
        os.makedirs(os.path.dirname(self.文件路径) or ".", exist_ok=True)
        with open(self.文件路径, "w", encoding="utf-8") as f:
            json.dump(self._数据, f, ensure_ascii=False, indent=2)

    @property
    def 已处理(self) -> dict[str, dict]:
        return self._数据.get("已处理", {})

    def 是否已处理(self, url: str) -> bool:
        """检查某个 URL 是否已经在缓存中（= 已处理过）"""
        return url.strip().rstrip("/") in self.已处理

    def 获取新url(self, url: str) -> Optional[str]:
        """获取已迁移模块的新 URL，不存在返回 None"""
        条目 = self.已处理.get(url.strip().rstrip("/"))
        if 条目:
            return 条目.get("新url")
        return None

    def 记录成功(self, 旧url: str, 新url: str, 仓库名: str = ""):
        """记录一次成功的迁移结果"""
        旧url = 旧url.strip().rstrip("/")
        if not 仓库名:
            仓库名 = 旧url.split("/")[-1].removesuffix(".git")

        self._数据.setdefault("已处理", {})[旧url] = {
            "新url": 新url,
            "仓库名": 仓库名,
            "处理时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._保存()

    def 批量记录(self, 映射表: dict[str, str]):
        """从映射表批量写入缓存"""
        for 旧url, 新url in 映射表.items():
            self.记录成功(旧url, 新url)

    def 刷新(self, url: str) -> bool:
        """
        从缓存中删除指定条目（--refresh 用）。
        下次 run 时该条目会被重新处理。
        """
        url = url.strip().rstrip("/")
        if url in self._数据.get("已处理", {}):
            del self._数据["已处理"][url]
            self._保存()
            return True
        return False

    def 刷新全部(self):
        """清空全部缓存（--refresh-all 用）"""
        self._数据["已处理"] = {}
        self._保存()

    def 数量(self) -> int:
        return len(self.已处理)

    def 获取所有映射(self) -> dict[str, str]:
        """返回 {旧url: 新url} 的扁平映射"""
        return {url: 信息["新url"] for url, 信息 in self.已处理.items() if "新url" in 信息}


# ─────────────────────────────────────────────
# 过滤逻辑（供 main.py 调用）
# ─────────────────────────────────────────────
def 过滤待处理列表(
    清单: 模块清单,
    缓存: 处理缓存,
    强制刷新: list[str] = None,
) -> list[str]:
    """
    从模块清单中过滤出本次需要实际处理的 URL 列表。
    逻辑：
        - 清单中有、缓存中没有 → 需要处理
        - 清单中有、缓存中有 → 跳过（除非在强制刷新列表中）
        - 强制刷新列表中的 → 先从缓存删除，然后加入待处理
    """
    强制刷新 = 强制刷新 or []

    # 先处理强制刷新
    for url in 强制刷新:
        缓存.刷新(url.strip().rstrip("/"))

    # 过滤
    待处理 = []
    for url in 清单.获取所有url():
        url = url.strip().rstrip("/")
        if 缓存.是否已处理(url):
            continue
        待处理.append(url)

    return 待处理
