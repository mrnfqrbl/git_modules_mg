"""
子仓库管理模块（递归迁移引擎）
==============================
核心流程（对每个条目）：
    1. 克隆目标仓库到本地缓存目录
    2. 读取该仓库的子模块(.gitmodules)和 Python 依赖(requirements/setup/pyproject)
    3. 对每个子依赖，独立克隆到缓存目录（不通过 submodule init）
    4. 递归处理子依赖直到没有更深层的引用
    5. 从最深层(n)开始向上(1)：推送到 gitee → 在引用方删除旧子模块 → 添加新 gitee URL 子模块 → 改写依赖文件
    6. 最终回到条目本身：提交变更 → 推送到 gitee

设计原则：
    - 每个仓库是同一个类的实例，自相似递归
    - 通过全局注册表去重（同一 URL 只处理一次）
    - 状态机保证环检测（处理中 → 再次进入 = 环 → 跳过）
    - 所有写操作前先探测（幂等）
    - 强制推送不考虑远程（只要确保远程原提交还在可以回溯即可）
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from lib.gdm import 函数通用返回模型
from lib.引用载体适配器 import 收集所有依赖, 改写所有引用, 检查引用是否已指向目标, 依赖边
from lib.util import 解决win权限问题

if TYPE_CHECKING:
    from lib.git_base_api import GiteeApi
    from lib.git_command import git操作


# ─────────────────────────────────────────────
# 处理状态
# ─────────────────────────────────────────────
class 处理状态:
    未开始   = "未开始"
    处理中   = "处理中"
    处理成功 = "处理成功"
    处理失败 = "处理失败"
    已跳过   = "已跳过"


# ─────────────────────────────────────────────
# 迁移上下文（所有实例共享）
# ─────────────────────────────────────────────
class 迁移上下文:
    """
    共享上下文对象，所有仓库任务实例引用同一份。
    包含：gitee_api、缓存目录、目标域名、注册表、映射表、日志。
    """

    def __init__(
        self,
        gitee_api: "GiteeApi",
        gitee用户名: str,
        缓存根目录: str,
        目标域名列表: list[str] = None,
        白名单域名: list[str] = None,
        dry_run: bool = False,
        logger=None,
    ):
        self.gitee_api = gitee_api
        self.gitee用户名 = gitee用户名
        self.缓存根目录 = 缓存根目录
        self.目标域名列表 = 目标域名列表 or ["gitee.com"]
        self.白名单域名 = 白名单域名 or ["gitee.com", "openi.pcl.ac.cn"]
        self.dry_run = dry_run
        self.logger = logger

        # 全局注册表：url → 仓库迁移任务实例（去重 + 环检测）
        self.注册表: dict[str, "仓库迁移任务"] = {}

        # 全局映射表：旧url → 新url（所有成功迁移的结果汇总）
        self.映射表: dict[str, str] = {}

        # 全部操作日志（审计用）
        self.全局日志: list[str] = []

    def 记录(self, 内容: str):
        时间戳 = datetime.now().strftime("%H:%M:%S")
        条目 = f"[{时间戳}] {内容}"
        self.全局日志.append(条目)
        if self.logger:
            self.logger.info(内容)

    def 确保缓存目录存在(self):
        os.makedirs(self.缓存根目录, exist_ok=True)


# ─────────────────────────────────────────────
# 仓库迁移任务（自相似，递归自实例化）
# ─────────────────────────────────────────────
class 仓库迁移任务:
    """
    单个仓库的迁移任务。
    每个实例代表"对某个仓库执行：克隆→读依赖→递归子任务→推送→改写引用"。
    通过上下文注册表去重，通过状态机检测环。
    """

    def __init__(self, url: str, 上下文: 迁移上下文, 父任务: Optional["仓库迁移任务"] = None):
        # 去重：如果注册表里已有，复用（调用方应先检查）
        self.url = url.rstrip("/")
        self.上下文 = 上下文
        self.父任务 = 父任务

        # 从 URL 推断仓库名
        self.仓库名 = self.url.split("/")[-1].removesuffix(".git")

        # 本地缓存路径
        self.本地路径 = os.path.join(上下文.缓存根目录, self.仓库名)

        # 迁移后的新 URL
        self.新url: Optional[str] = None

        # 状态
        self.状态 = 处理状态.未开始
        self.开始时间: Optional[datetime] = None
        self.结束时间: Optional[datetime] = None
        self.操作日志: list[str] = []

        # 子任务（子模块 + 依赖 统一管理）
        self.子任务列表: list["仓库迁移任务"] = []

        # 注册到上下文
        上下文.注册表[self.url] = self

    # ── 日志 ─────────────────────────────────────────────────

    def _记录(self, 内容: str):
        时间戳 = datetime.now().strftime("%H:%M:%S")
        self.操作日志.append(f"[{时间戳}] {内容}")
        self.上下文.记录(f"[{self.仓库名}] {内容}")

    # ── 主流程 ───────────────────────────────────────────────

    def 执行(self) -> 函数通用返回模型:
        """
        主入口：执行完整的迁移流程。
        返回 函数通用返回模型（状态=True/False, 数据=处理摘要）
        """
        返回 = 函数通用返回模型()

        # ── 环检测 ──
        if self.状态 == 处理状态.处理中:
            self._记录("⚠ 检测到环引用，跳过")
            self.状态 = 处理状态.已跳过
            返回.成功(数据={"状态": "已跳过", "原因": "环引用"})
            return 返回

        # ── 已处理过 ──
        if self.状态 in (处理状态.处理成功, 处理状态.已跳过):
            返回.成功(数据={"状态": self.状态, "新url": self.新url})
            return 返回

        # ── 检查是否已指向目标平台（无需迁移） ──
        if 检查引用是否已指向目标(self.url, self.上下文.白名单域名):
            self._记录(f"已在目标平台，跳过：{self.url}")
            self.状态 = 处理状态.已跳过
            self.新url = self.url
            返回.成功(数据={"状态": "已跳过", "原因": "已在目标平台"})
            return 返回

        # ── 开始处理 ──
        self.状态 = 处理状态.处理中
        self.开始时间 = datetime.now()
        self._记录(f"开始处理：{self.url}")

        try:
            # 步骤1：克隆到缓存目录
            self._步骤_克隆()

            # 步骤2：读取子模块和依赖
            依赖列表 = self._步骤_读取依赖()

            # 步骤3：对每个依赖递归创建子任务并执行
            self._步骤_递归处理子依赖(依赖列表)

            # 步骤4：改写本仓库中的引用文件
            self._步骤_改写引用()

            # 步骤5：提交本地变更
            self._步骤_提交变更()

            # 步骤6：推送到 Gitee（先确保远端仓库存在）
            self._步骤_推送到gitee()

            # 完成
            self.状态 = 处理状态.处理成功
            self.结束时间 = datetime.now()
            self._记录(f"处理成功 → {self.新url}")

            # 写入全局映射表
            self.上下文.映射表[self.url] = self.新url

            返回.成功(数据=self._生成摘要())

        except Exception as e:
            self.状态 = 处理状态.处理失败
            self.结束时间 = datetime.now()
            self._记录(f"处理失败：{str(e)}")
            返回.失败(错误信息=f"仓库 {self.仓库名} 迁移失败：{str(e)}", 异常对象=e)

        return 返回

    # ── 步骤实现 ─────────────────────────────────────────────

    def _步骤_克隆(self):
        """克隆远程仓库到缓存目录（如果已存在则跳过）"""
        from lib.git_command import Git工具

        if os.path.isdir(self.本地路径) and os.path.exists(os.path.join(self.本地路径, ".git")):
            self._记录(f"本地缓存已存在，复用：{self.本地路径}")
            return

        # 清理残留（非 git 目录）
        if os.path.exists(self.本地路径):
            shutil.rmtree(self.本地路径, onerror=解决win权限问题)

        self._记录(f"克隆中：{self.url} → {self.本地路径}")

        if self.上下文.dry_run:
            self._记录("[dry-run] 跳过实际克隆")
            return

        结果 = Git工具.clone(self.url, self.本地路径)
        if not 结果.状态:
            raise RuntimeError(f"克隆失败：{结果.错误信息}")

    def _步骤_读取依赖(self) -> list[依赖边]:
        """读取仓库中的子模块和 Python 依赖"""
        if self.上下文.dry_run and not os.path.isdir(self.本地路径):
            self._记录("[dry-run] 本地路径不存在，跳过依赖读取")
            return []

        依赖列表 = 收集所有依赖(self.本地路径)
        self._记录(f"发现 {len(依赖列表)} 条外部引用")

        for 边 in 依赖列表:
            self._记录(f"  → [{边.引用类型}] {边.仓库名} @ {边.url}")

        return 依赖列表

    def _步骤_递归处理子依赖(self, 依赖列表: list[依赖边]):
        """对每个依赖创建子任务并执行（独立克隆，不走 submodule init）"""
        for 边 in 依赖列表:
            # 检查是否已在目标平台
            if 检查引用是否已指向目标(边.url, self.上下文.白名单域名):
                self._记录(f"  跳过（已在目标平台）：{边.仓库名}")
                continue

            # 检查注册表（去重）
            if 边.url in self.上下文.注册表:
                已有任务 = self.上下文.注册表[边.url]
                self.子任务列表.append(已有任务)

                # 如果还没处理完，执行它（会触发环检测）
                if 已有任务.状态 == 处理状态.未开始:
                    已有任务.执行()
                elif 已有任务.状态 == 处理状态.处理中:
                    # 环引用
                    self._记录(f"  检测到环引用，跳过：{边.仓库名}")
                # 其他状态（成功/失败/跳过）不需要再次执行
                continue

            # 创建新的子任务
            子任务 = 仓库迁移任务(
                url=边.url,
                上下文=self.上下文,
                父任务=self,
            )
            self.子任务列表.append(子任务)

            # 递归执行
            子任务.执行()

    def _步骤_改写引用(self):
        """
        按正确顺序改写本仓库中的所有引用：
          1. 先做 git 级别的子模块替换（删旧子模块 → 添新 URL 子模块）
             必须在文本改写前，此时 .gitmodules 里还是旧 URL，能正确匹配映射表
          2. 再做文本兜底改写（requirements / pyproject / .gitmodules 残余）
             git 级别替换完成后 .gitmodules 已更新，文本改写幂等跳过已改项
        """
        if not self.上下文.映射表:
            self._记录("无需改写（映射表为空）")
            return

        if self.上下文.dry_run and not os.path.isdir(self.本地路径):
            self._记录("[dry-run] 跳过改写")
            return

        # 步骤 1：git 级别替换（用旧 URL 索引，必须先于文本改写）
        self._处理子模块替换()

        # 步骤 2：文本兜底改写所有引用载体文件
        改动 = 改写所有引用(self.本地路径, self.上下文.映射表)
        if 改动:
            for 条目 in 改动:
                self._记录(f"  改写：{条目}")
        else:
            self._记录("引用文件中无需文本改写的匹配项")

    def _处理子模块替换(self):
        """
        git 级别子模块替换：删除旧子模块 → 重新添加 gitee URL 子模块。
        确保 .git/config、.gitmodules、实际子模块目录全部正确对齐。
        调用时机：必须在文本改写 .gitmodules 之前，否则旧 URL 无法匹配映射表。
        """
        from lib.git_command import Git工具

        if not os.path.isdir(self.本地路径):
            return

        # 检查是否是有效 git 仓库
        有效性 = Git工具.是否为有效仓库(self.本地路径)
        if not 有效性.状态 or not 有效性.数据:
            return

        try:
            仓库实例 = Git工具(self.本地路径)
        except Exception:
            return

        # 获取当前子模块列表
        子模块结果 = 仓库实例.获取子模块列表()
        if not 子模块结果.状态 or not 子模块结果.数据:
            return

        for 子模块 in 子模块结果.数据:
            旧url = 子模块["URL"]
            if 旧url not in self.上下文.映射表:
                continue

            新url = self.上下文.映射表[旧url]
            名称 = 子模块["名称"]
            路径 = 子模块["路径"]
            分支 = 子模块.get("追踪分支", None)

            self._记录(f"  替换子模块：{名称} → {新url}")

            # 删除旧子模块
            删除结果 = 仓库实例.删除子模块(名称)
            if not 删除结果.状态:
                self._记录(f"  ⚠ 删除子模块失败：{删除结果.错误信息}，跳过")
                continue

            # 重新添加新 URL 子模块
            添加结果 = 仓库实例.添加子模块(名称, 路径, 新url, 分支=分支)
            if not 添加结果.状态:
                self._记录(f"  ⚠ 添加子模块失败：{添加结果.错误信息}")

    def _步骤_提交变更(self):
        """提交本地改动"""
        from lib.git_command import Git工具

        if self.上下文.dry_run:
            self._记录("[dry-run] 跳过提交")
            return

        if not os.path.isdir(self.本地路径):
            return

        有效性 = Git工具.是否为有效仓库(self.本地路径)
        if not 有效性.状态 or not 有效性.数据:
            return

        仓库实例 = Git工具(self.本地路径)

        # 检查是否有变更需要提交
        脏检查 = 仓库实例.是否有未提交更改()
        if not 脏检查.状态 or not 脏检查.数据:
            self._记录("无变更需要提交")
            return

        提交结果 = 仓库实例.提交(
            提交信息=f"[git_modules_mg] 迁移引用至 gitee（自动）",
            是否允许自动add=True
        )
        if 提交结果.状态:
            self._记录(f"提交成功：{提交结果.数据}")
        else:
            self._记录(f"⚠ 提交失败：{提交结果.错误信息}")

    def _步骤_推送到gitee(self):
        """确保 gitee 上仓库存在 → 添加 remote → 强制推送"""
        from lib.git_command import Git工具

        # 构造目标 URL
        目标url = f"https://gitee.com/{self.上下文.gitee用户名}/{self.仓库名}.git"
        self.新url = 目标url

        if self.上下文.dry_run:
            self._记录(f"[dry-run] 目标URL：{目标url}")
            return

        # 确保 gitee 仓库存在
        self._确保gitee仓库存在()

        # 添加/更新 remote
        if not os.path.isdir(self.本地路径):
            return

        有效性 = Git工具.是否为有效仓库(self.本地路径)
        if not 有效性.状态 or not 有效性.数据:
            return

        仓库实例 = Git工具(self.本地路径)

        # 设置 gitee remote
        try:
            # 先尝试删除已存在的 gitee remote
            仓库实例.repo.git.remote("remove", "gitee")
        except Exception:
            pass

        try:
            仓库实例.repo.git.remote("add", "gitee", 目标url)
        except Exception:
            pass

        # 强制推送所有分支和 tags
        self._记录(f"推送到 gitee：{目标url}")
        try:
            # 推送所有分支
            仓库实例.repo.git.push("gitee", "--all", "--force")
            # 推送所有 tags
            仓库实例.repo.git.push("gitee", "--tags", "--force")
            self._记录("推送成功（全部分支 + tags）")
        except Exception as e:
            # 退化：只推送当前分支
            self._记录(f"⚠ 全量推送失败，尝试推送当前分支：{str(e)}")
            推送结果 = 仓库实例.推送(远程名称="gitee", 强制=True)
            if not 推送结果.状态:
                raise RuntimeError(f"推送失败：{推送结果.错误信息}")

    def _确保gitee仓库存在(self):
        """检查 gitee 是否已有同名仓库，没有则创建"""
        try:
            self.上下文.gitee_api.获取仓库信息(self.仓库名)
            self._记录(f"Gitee 仓库已存在：{self.仓库名}")
        except Exception:
            # 不存在，创建
            self._记录(f"创建 Gitee 仓库：{self.仓库名}")
            try:
                self.上下文.gitee_api.创建仓库(self.仓库名, 描述=f"镜像自 {self.url}", 私有=False)
                self._记录(f"创建成功")
            except Exception as e:
                # 可能是因为已存在但 API 返回异常格式
                self._记录(f"⚠ 创建仓库异常（可能已存在）：{str(e)}")

    # ── 结果输出 ─────────────────────────────────────────────

    def _生成摘要(self) -> dict:
        return {
            "仓库名": self.仓库名,
            "原始url": self.url,
            "新url": self.新url,
            "状态": self.状态,
            "子任务数": len(self.子任务列表),
            "开始时间": self.开始时间.strftime("%Y-%m-%d %H:%M:%S") if self.开始时间 else None,
            "结束时间": self.结束时间.strftime("%Y-%m-%d %H:%M:%S") if self.结束时间 else None,
            "操作日志": self.操作日志,
        }

    def __repr__(self):
        return f"<仓库迁移任务 {self.仓库名} [{self.状态}]>"


# ─────────────────────────────────────────────
# 批量执行入口（供 main.py 调用）
# ─────────────────────────────────────────────
def 批量迁移(
    待处理列表: list[str],
    gitee_api: "GiteeApi",
    gitee用户名: str,
    缓存根目录: str,
    目标域名列表: list[str] = None,
    白名单域名: list[str] = None,
    dry_run: bool = False,
    logger=None,
) -> 函数通用返回模型:
    """
    批量迁移入口。
    :param 待处理列表: 需要迁移的仓库 URL 列表
    :param gitee_api: GiteeApi 实例
    :param gitee用户名: gitee 用户名
    :param 缓存根目录: 本地克隆缓存目录
    :param 目标域名列表: 目标平台域名（用于判断"已迁移"）
    :param 白名单域名: 白名单域名（已在这些域名上的不迁移）
    :param dry_run: 是否只做计划不执行
    :param logger: 日志器
    :return: 函数通用返回模型
    """
    返回 = 函数通用返回模型()

    # 构造共享上下文
    上下文 = 迁移上下文(
        gitee_api=gitee_api,
        gitee用户名=gitee用户名,
        缓存根目录=缓存根目录,
        目标域名列表=目标域名列表,
        白名单域名=白名单域名,
        dry_run=dry_run,
        logger=logger,
    )
    上下文.确保缓存目录存在()

    # 逐个处理
    结果列表 = []
    for url in 待处理列表:
        url = url.strip()
        if not url:
            continue

        # 跳过已在目标平台的
        if 检查引用是否已指向目标(url, 上下文.白名单域名):
            上下文.记录(f"跳过（已在目标平台）：{url}")
            结果列表.append({"url": url, "状态": "已跳过", "原因": "已在目标平台"})
            continue

        # 检查注册表
        if url in 上下文.注册表:
            上下文.记录(f"跳过（重复条目）：{url}")
            结果列表.append({"url": url, "状态": "已跳过", "原因": "重复"})
            continue

        # 创建任务并执行
        任务 = 仓库迁移任务(url=url, 上下文=上下文)
        任务结果 = 任务.执行()
        结果列表.append({
            "url": url,
            "状态": 任务.状态,
            "新url": 任务.新url,
            "详情": 任务结果.数据 if 任务结果.状态 else 任务结果.错误信息,
        })

    # 汇总
    成功数 = sum(1 for r in 结果列表 if r["状态"] in (处理状态.处理成功, 处理状态.已跳过))
    失败数 = len(结果列表) - 成功数

    返回.成功(数据={
        "总数": len(结果列表),
        "成功": 成功数,
        "失败": 失败数,
        "映射表": dict(上下文.映射表),
        "详情": 结果列表,
        "全局日志": 上下文.全局日志,
    })

    return 返回
