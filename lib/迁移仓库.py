from __future__ import annotations

# TODO: 处理依赖 包括 requirements.txt setup.py pyproject.toml
# TODO: 任务类自包含处理逻辑，向下递归构造子任务实例，省略外部额外递归调用
# TODO: 采用新分支构造来实现基于原提交变更后推送到指定命名分支，由外部仓库更新引用
# TODO: comfyui 插件是否需要保持 commit hash 不变——目前按"不强制"处理，下次迁移以源端当前 HEAD 为准

# TODO: debug 情况下错误信息将不再是字符串而是 log 列表
# TODO: 对于这里的log或者说操作记录和状态相关的信息强制返回和做缓存 我可以不看你不可以没有

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, TYPE_CHECKING

from lib.gdm import 函数通用返回模型

if TYPE_CHECKING:
    from lib.git_base_api import GiteeApi
    from lib.git_command import Git工具


# ─────────────────────────────────────────────
# 处理状态枚举（修复：原来两个成员都叫 处理 导致后者覆盖前者）
# ─────────────────────────────────────────────
class 处理状态(Enum):
    未开始   = "未开始"
    处理中   = "处理中"
    处理成功 = "处理成功"   # 原来 处理 = "成功" 和 处理 = "失败" 重名，已修复
    处理失败 = "处理失败"
    已跳过   = "已跳过"


# ─────────────────────────────────────────────
# 单一仓库任务类
# 同一 URL 全局只有一个实例（通过 __new__ 注册表保证）
# 上下文（gitee_api / git工具 / 仓库目录）由调用方注入，所有实例共享同一份
# ─────────────────────────────────────────────
class 仓库任务:
    """
    自相似仓库任务类。
    每个实例代表"对某一个仓库执行迁移"这件事，
    内部递归构造子仓库任务实例，形成隐式任务树。

    生命周期：
        实例化 → 开始处理() → [子任务递归] → 标记成功() / 标记失败()
    """

    # 全局注册表：url → 实例，防止同一次运行里重复实例化
    _实例表: dict[str, "仓库任务"] = {}

    def __new__(cls, url: str, *args, **kwargs):
        if url in cls._实例表:
            return cls._实例表[url]
        实例 = super().__new__(cls)
        cls._实例表[url] = 实例
        return 实例

    def __init__(
        self,
        url: str,
        gitee_api: "GiteeApi",
        git工具: "Git工具",
        仓库目录: str,
        父任务: Optional["仓库任务"] = None,
    ):
        # __new__ 复用时 __init__ 会再次被调用，用标志位跳过重复初始化
        if getattr(self, "_已初始化", False):
            return

        self.url = url
        self.gitee_api = gitee_api
        self.git工具 = git工具
        self.仓库目录 = 仓库目录
        self.父任务 = 父任务

        # 从 URL 推断仓库名（github.com/user/repo.git → repo）
        self.仓库名 = url.rstrip("/").split("/")[-1].removesuffix(".git")

        # 本地缓存路径
        import os
        self.本地路径 = os.path.join(仓库目录, self.仓库名)

        # 迁移结果
        self.新url: Optional[str] = None

        # 状态与计时
        self.处理状态 = 处理状态.未开始
        self.开始时间: Optional[datetime] = None
        self.结束时间: Optional[datetime] = None
        self.处理耗时: Optional[timedelta] = None

        # 日志与子任务
        self.操作日志: list[str] = []
        self.子仓库任务列表: list["仓库任务"] = []
        self.依赖任务列表: list["仓库任务"] = []

        self._已初始化 = True

    # ── 状态流转 ─────────────────────────────────────────────────

    def 开始处理(self):
        if self.处理状态 == 处理状态.处理中:
            # 再次进入 = 检测到环，直接标记跳过
            self.处理状态 = 处理状态.已跳过
            self._记录日志(f"⚠ 检测到环引用，跳过：{self.url}")
            return
        self.处理状态 = 处理状态.处理中
        self.开始时间 = datetime.now()
        self._记录日志(f"开始处理：{self.url}")

    def 标记成功(self, 新url: str):
        self.处理状态 = 处理状态.处理成功
        self.新url = 新url
        self._结束计时()
        self._记录日志(f"处理成功 → {新url}")

    def 标记失败(self, 错误信息: str):
        self.处理状态 = 处理状态.处理失败
        self._结束计时()
        self._记录日志(f"处理失败：{错误信息}")

    def 标记跳过(self, 原因: str, 新url: str = ""):
        self.处理状态 = 处理状态.已跳过
        if 新url:
            self.新url = 新url
        self._结束计时()
        self._记录日志(f"跳过（{原因}）")

    # ── 内部工具 ─────────────────────────────────────────────────

    def _结束计时(self):
        self.结束时间 = datetime.now()
        if self.开始时间:
            self.处理耗时 = self.结束时间 - self.开始时间

    def _记录日志(self, 内容: str):
        时间戳 = datetime.now().strftime("%H:%M:%S")
        self.操作日志.append(f"[{时间戳}] {内容}")

    # ── 结果输出 ─────────────────────────────────────────────────

    def 获取处理结果(self) -> 函数通用返回模型:
        """返回本任务的处理摘要，供上层汇总报告使用"""
        返回 = 函数通用返回模型()
        成功 = self.处理状态 in (处理状态.处理成功, 处理状态.已跳过)
        数据 = {
            "仓库名称":   self.仓库名,
            "原始url":    self.url,
            "新url":      self.新url,
            "处理状态":   self.处理状态.value,
            "子仓库数量": len(self.子仓库任务列表),
            "依赖数量":   len(self.依赖任务列表),
            "开始时间":   self.开始时间.strftime("%Y-%m-%d %H:%M:%S") if self.开始时间 else None,
            "结束时间":   self.结束时间.strftime("%Y-%m-%d %H:%M:%S") if self.结束时间 else None,
            "处理耗时秒": round(self.处理耗时.total_seconds(), 2) if self.处理耗时 else None,
            "操作日志":   self.操作日志,
            "子任务结果": [子.获取处理结果().转字典() for 子 in self.子仓库任务列表],
            "依赖结果":   [依.获取处理结果().转字典() for 依 in self.依赖任务列表],
        }
        if 成功:
            返回.成功(数据=数据)
        else:
            返回.失败(错误信息=f"仓库处理失败：{self.仓库名}", 数据=数据)
        return 返回

    def 转字典(self) -> dict:
        """完整字典（用于 JSON 溯源报告）"""
        return self.获取处理结果().转字典()

    def __repr__(self):
        return f"<仓库任务 {self.仓库名} [{self.处理状态.value}]>"

    # ── 类级工具 ─────────────────────────────────────────────────

    @classmethod
    def 清空注册表(cls):
        """单次运行结束后调用，重置全局状态（测试/多轮运行用）"""
        cls._实例表.clear()
