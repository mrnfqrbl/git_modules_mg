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
import git
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from lib.gdm import 函数通用返回模型
from lib.引用载体适配器 import 收集所有依赖, 改写所有引用, 检查引用是否已指向目标, 依赖边
from lib.util import 解决win权限问题
from lib.缓存管理 import 处理缓存

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


def _is_specific_tag_or_commit(ref: str) -> bool:
    if not ref:
        return False
    # 常见的分支/开发主干名不是具体 tag/commit
    if ref.lower() in {"main", "master", "dev", "develop", "release", "head"}:
        return False
    # 如果包含类似 feature/ 或 dev/ 的分支路径结构，也不是 tag/commit
    if "/" in ref:
        lower_ref = ref.lower()
        if any(lower_ref.startswith(prefix) for prefix in ["feature/", "bugfix/", "hotfix/", "support/", "test/"]):
            return False
    return True



# ─────────────────────────────────────────────
# 迁移上下文（所有实例共享）
# ─────────────────────────────────────────────
class 迁移上下文:
    """
    共享上下文对象，所有仓库任务实例引用同一份。
    包含：gitee_api、缓存目录、目标域名、注册表、映射表、日志、处理缓存。
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
        处理缓存实例: "处理缓存" = None,
        no_push: bool = False,
        public: bool = True,
    ):
        self.gitee_api = gitee_api
        self.gitee用户名 = gitee用户名
        self.缓存根目录 = 缓存根目录
        self.目标域名列表 = 目标域名列表 or ["gitee.com"]
        self.白名单域名 = 白名单域名 or ["gitee.com", "openi.pcl.ac.cn"]
        self.dry_run = dry_run
        self.logger = logger
        self.no_push = no_push
        self.public = public

        # 新增：持有处理缓存实例引用，迁移完成后直接写入
        self.处理缓存 = 处理缓存实例

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

    def __init__(self, url: str, 上下文: 迁移上下文, 父任务: Optional["仓库迁移任务"] = None, 锁定commit: str = "", 子模块快照: dict = None, 重写仓库名: str = ""):
        # 去重：如果注册表里已有，复用（调用方应先检查）
        self.url = url.rstrip("/")
        self.上下文 = 上下文
        self.父任务 = 父任务

        # 从 URL 推断仓库名
        if 重写仓库名:
            self.仓库名 = 重写仓库名
        else:
            self.仓库名 = self.url.replace("\\", "/").split("/")[-1].removesuffix(".git")

        # 本地缓存路径
        self.本地路径 = os.path.join(上下文.缓存根目录, self.仓库名)

        # 迁移后的新 URL
        self.新url: Optional[str] = None
        self.锁定commit = 锁定commit        # 父级锁定的 commit hash
        self.子模块快照 = 子模块快照          # {"名称","路径","追踪分支"} 用于溯源
        self.新commit: Optional[str] = None  # 迁移后本仓库的 HEAD commit
        self.原始commit: str = ""            # 本地克隆后记录的原始 HEAD commit
        self.替换对: dict[str, str] = {}      # 记录子模块替换记录

        # 状态
        self.状态 = 处理状态.未开始
        self.开始时间: Optional[datetime] = None
        self.结束时间: Optional[datetime] = None
        self.操作日志: list[str] = []

        # 子任务（子模块 + 依赖 统一管理）
        self.子任务列表: list["仓库迁移任务"] = []
        self.默认分支: str = "master"        # 本地活跃的主分支名（默认为 master）

        # 解析 URL 信息以生成美化日志标识前缀
        try:
            # 去除协议和SSH前缀并兼容 Windows 分隔符
            temp = self.url.replace("https://", "").replace("http://", "").replace("git@", "").replace("\\", "/")
            temp = temp.replace(":", "/")  # SSH格式兼容
            parts = [p for p in temp.split("/") if p]
            domain = parts[0].split(".")[0]  # github / gitee
            owner = parts[1]  # mrnfqrbl / mrnf
            repo = parts[2].split(".git")[0] if len(parts) > 2 else parts[-1].split(".git")[0]
        except Exception:
            domain = "git"
            owner = "unknown"
            repo = self.仓库名

        # 提取子模块名称
        子模块名 = ""
        if self.子模块快照 and "名称" in self.子模块快照:
            子模块名 = self.子模块快照["名称"]

        # 组装高可读性日志前缀
        if 子模块名:
            self.日志标识 = f"{子模块名} - {domain}-{owner}/{repo}"
        else:
            self.日志标识 = f"{domain}-{owner}/{repo}"

        # 注册到上下文并归一化双向注册
        上下文.注册表[self.url] = self
        def 注册变体(u: str):
            clean_u = u.rstrip("/")
            if clean_u.endswith(".git"):
                无后缀 = clean_u.removesuffix(".git")
                带后缀 = clean_u
            else:
                无后缀 = clean_u
                带后缀 = clean_u + ".git"
            上下文.注册表[无后缀] = self
            上下文.注册表[带后缀] = self

        注册变体(self.url)
        # 计算并注册 Gitee URL
        gitee_url = f"https://gitee.com/{上下文.gitee用户名}/{self.仓库名}.git"
        注册变体(gitee_url)

    # ── 日志 ─────────────────────────────────────────────────

    def _记录(self, 内容: str):
        时间戳 = datetime.now().strftime("%H:%M:%S")
        self.操作日志.append(f"[{时间戳}] {内容}")
        self.上下文.记录(f"[{self.日志标识}] {内容}")

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
            # 步骤1：克隆（不变）
            self._步骤_克隆()

            # 提前记录默认的活跃分支名，以防止 detached HEAD 无法推送或拉取该分支的新提交
            try:
                from lib.git_command import Git工具
                temp_git = Git工具(self.本地路径)
                self.默认分支 = temp_git.repo.active_branch.name
            except Exception:
                try:
                    # 如果未处于任何具体分支，尝试获取 origin/HEAD 指向的活跃分支
                    active_ref = temp_git.repo.git.symbolic_ref("refs/remotes/origin/HEAD")
                    self.默认分支 = active_ref.split("/")[-1]
                except Exception:
                    self.默认分支 = "master"

            # 步骤1.5（新增）：如果有锁定commit，checkout 到该 commit
            if self.锁定commit:
                self._步骤_checkout锁定commit()

            # 步骤2：读取依赖（不变）
            依赖列表 = self._步骤_读取依赖()

            # 记录原始commit
            from lib.git_command import Git工具
            仓库实例 = Git工具(self.本地路径)
            head_res = 仓库实例.获取HEAD()
            self.原始commit = self.锁定commit if self.锁定commit else (head_res.数据 if head_res.状态 else "")

            # 尝试提前复用已有仓库（第一防线与第二防线校验）
            if not self.上下文.dry_run and not self.上下文.no_push:
                try:
                    res = self._扫描匹配的已存在仓库(self.仓库名, 依赖列表, self.原始commit)
                    if res:
                        found_name, reuse_commit, child_mappings = res
                        self._记录(f"🌟 发现匹配的已存在 Gitee 仓库 {found_name}，直接复用提交 {reuse_commit[:8]}，安全跳过后续所有子任务与推送！")
                        self.仓库名 = found_name
                        self.新url = f"https://gitee.com/{self.上下文.gitee用户名}/{found_name}.git"
                        self.新commit = reuse_commit
                        
                        # 写入全局映射表和注册表
                        self.上下文.映射表[self.url] = self.新url
                        for orig_url, new_url in child_mappings.items():
                            self.上下文.映射表[orig_url] = new_url
                            
                        # 双重注册到注册表，确保引用方可以通过原始或目标 URL 查找到此任务实例
                        self.上下文.注册表[self.url] = self
                        self.上下文.注册表[self.新url] = self
                        self.上下文.注册表[self.新url.removesuffix(".git")] = self
                        
                        # 标记状态为处理成功
                        self.状态 = 处理状态.处理成功
                        self.结束时间 = datetime.now()
                        self._步骤_写入缓存()
                        
                        # [新需求] 即使跳过，也要更新自身仓库属性并递归处理子依赖来更新其子仓库属性
                        self._更新gitee仓库属性()
                        self._步骤_递归处理子依赖(依赖列表)
                        
                        返回.成功(数据=self._生成摘要())
                        return 返回
                except Exception as ex:
                    self._记录(f"  扫描/校验已有 Gitee 仓库时发生异常（将继续迁移）：{str(ex)}")

            # 步骤3：递归子依赖（改动：传入锁定commit）
            self._步骤_递归处理子依赖(依赖列表)

            # 步骤4：改写引用（不变：先 git 级删/建子模块，再文本兜底）
            self._步骤_改写引用()

            # 步骤5：提交（不变）
            self._步骤_提交变更()

            # 步骤5.5（新增）：取当前 HEAD 作为"迁移后commit"
            self._步骤_记录新commit()

            # 步骤6：推送到 gitee（不变）
            if not self.上下文.no_push:
                self._步骤_推送到gitee()

            # 步骤7（新增）：写入缓存记录
            self._步骤_写入缓存()

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

    def _解析提交信息(self, message: str) -> tuple[bool, str, dict]:
        """解析提交消息，返回 (是否是有效格式, 原始commit_sha, 映射关系dict)"""
        if not message:
            return False, "", {}
        lines = [line.strip() for line in message.split("\n") if line.strip()]
        if not lines or not any("[git_modules_mg]" in line for line in lines):
            return False, "", {}

        orig_commit = ""
        mappings = {}
        in_mappings = False

        for line in lines:
            if line.startswith("原始commit:"):
                orig_commit = line.replace("原始commit:", "").strip()
            elif line.startswith("依赖映射:"):
                in_mappings = True
            elif in_mappings and line.startswith("-"):
                # 格式: - 旧url -> 新url
                content = line.lstrip("-").strip()
                if "->" in content:
                    parts = content.split("->")
                    if len(parts) == 2:
                        mappings[parts[0].strip()] = parts[1].strip()
            elif in_mappings and not line.startswith("-"):
                in_mappings = False

        return True, orig_commit, mappings

    def _尝试获取原始url(self, 边_仓库名: str, gitee_url: str) -> Optional[str]:
        """寻找或猜测该 Gitee 仓库的原始 GitHub URL"""
        # 1. 尝试从当前已克隆仓库本地的 .gmm_map.json 寻找
        map_path = os.path.join(self.本地路径, ".gmm_map.json")
        if os.path.isfile(map_path):
            try:
                import json
                with open(map_path, "r", encoding="utf-8") as f:
                    gmm_data = json.load(f)
                    for item in gmm_data.get("子依赖列表", []):
                        if item.get("新url") == gitee_url or item.get("新url", "").rstrip("/").removesuffix(".git") == gitee_url.rstrip("/").removesuffix(".git"):
                            return item.get("原始url")
            except Exception:
                pass
        
        # 2. 尝试从缓存中查找
        if self.上下文.处理缓存:
            for k, v in self.上下文.处理缓存.条目表.items():
                rec = v.get("记录", [])
                if rec and (rec[0].get("新url") == gitee_url or rec[0].get("新url", "").rstrip("/").removesuffix(".git") == gitee_url.rstrip("/").removesuffix(".git")):
                    return k

        # 3. 尝试从 Gitee API 请求获取 .gmm_map.json 来读取
        try:
            content = self.上下文.gitee_api.获取文件内容(边_仓库名, ".gmm_map.json")
            if content:
                import json
                gmm_data = json.loads(content)
                if isinstance(gmm_data, dict) and gmm_data.get("原始url"):
                    return gmm_data["原始url"]
        except Exception:
            pass

        return None

    def _是否为本仓库的镜像(self, 仓库名: str) -> bool:
        """
        判断指定的 Gitee 仓库是否是当前源仓库 the 镜像
        """
        # 1. 优先使用快速描述匹配（作为判定手段之一，但由于不稳定，若匹配直接返回 True，不匹配则通过下面内容判断）
        try:
            仓库信息 = self.上下文.gitee_api.获取仓库信息(仓库名)
            期望描述 = f"镜像自 {self.url}"
            if 仓库信息.get("描述", "") == 期望描述:
                return True
        except Exception:
            pass

        # 2. 从 .gmm_map.json 校验原始 url (最核心最稳定的判定)
        try:
            content = self.上下文.gitee_api.获取文件内容(仓库名, ".gmm_map.json")
            if content:
                import json
                gmm_data = json.loads(content)
                if isinstance(gmm_data, dict):
                    gmm_orig_url = gmm_data.get("原始url", "").rstrip("/").removesuffix(".git")
                    expected_orig_url = self.url.rstrip("/").removesuffix(".git")
                    if gmm_orig_url == expected_orig_url:
                        return True
        except Exception:
            pass

        return False

    def _寻找已有的本仓库镜像(self) -> Optional[str]:
        """
        在 Gitee 上探测已属于当前源仓库的镜像名称，防止无限顺位
        """
        连续不存在次数 = 0
        最大连续不存在 = 3
        最大尝试 = 50
        
        候选名称列表 = [self.仓库名] + [f"{self.仓库名}_{i}" for i in range(1, 最大尝试 + 1)]
        
        for name in 候选名称列表:
            if not self.上下文.gitee_api.仓库是否存在(name):
                连续不存在次数 += 1
                if 连续不存在次数 >= 最大连续不存在:
                    break
                continue
            
            连续不存在次数 = 0
            
            if self._是否为本仓库的镜像(name):
                return name
                
        return None

    def _扫描匹配的已存在仓库(self, 基础名称: str, 预期依赖列表: list[依赖边], 预期原始commit: str) -> Optional[tuple[str, str, dict[str, str]]]:
        """
        扫描基础名称及顺位名称，寻找内容匹配（.gmm_map.json 或提交消息）的已有仓库进行复用
        """
        连续不存在次数 = 0
        最大连续不存在 = 3
        最大尝试 = 50
        
        候选名称列表 = [基础名称] + [f"{基础名称}_{i}" for i in range(1, 最大尝试 + 1)]
        
        for name in 候选名称列表:
            if not self.上下文.gitee_api.仓库是否存在(name):
                连续不存在次数 += 1
                if 连续不存在次数 >= 最大连续不存在:
                    break
                continue
            
            连续不存在次数 = 0
            
            if self._是否为本仓库的镜像(name):
                is_valid, reuse_commit, child_mappings = self._检查目标平台仓库是否有效(name, 预期依赖列表, 预期原始commit)
                if is_valid:
                    return name, reuse_commit, child_mappings
                    
        return None

    def _检查目标平台仓库是否有效(self, 仓库名: str, 预期依赖列表: list[依赖边], 预期原始commit: str) -> tuple[bool, str, dict[str, str]]:
        """
        双重防线深度校验目标平台的仓库是否可以直接复用。
        返回 (是否有效, 复用commit_sha, 子依赖映射关系)
        """
        child_mappings = {}
        
        # 第一防线：校验 .gmm_map.json 元数据
        try:
            content = self.上下文.gitee_api.获取文件内容(仓库名, ".gmm_map.json")
            if content:
                import json
                gmm_data = json.loads(content)
                if isinstance(gmm_data, dict):
                    # 1. 校验 原始url (若存在该字段)
                    gmm_orig_url = gmm_data.get("原始url", "")
                    if gmm_orig_url:
                        gmm_orig_url_clean = gmm_orig_url.rstrip("/").removesuffix(".git")
                        expected_orig_url_clean = self.url.rstrip("/").removesuffix(".git")
                        if gmm_orig_url_clean != expected_orig_url_clean:
                            return False, "", {}
                    
                    # 2. 校验 原始commit
                    gmm_orig_commit = gmm_data.get("原始commit", "")
                    if gmm_orig_commit != 预期原始commit:
                        return False, "", {}
                    
                    # 3. 检查所有子依赖映射是否完全对齐
                    all_aligned = True
                    gmm_children = gmm_data.get("子依赖列表", [])
                    
                    gmm_child_map = {}
                    for child in gmm_children:
                        p = child.get("路径", "").replace("\\", "/")
                        ou = child.get("原始url", "").rstrip("/").removesuffix(".git")
                        oc = child.get("原始commit", "")
                        gmm_child_map[(p, ou)] = oc
                        
                        orig_url = child.get("原始url")
                        new_url = child.get("新url")
                        if orig_url and new_url:
                            child_mappings[orig_url] = new_url
                    
                    for 边 in 预期依赖列表:
                        p = 边.路径 if 边.引用类型 == "子模块" else f"submodules/{边.仓库名}"
                        p = p.replace("\\", "/")
                        ou = 边.url.rstrip("/").removesuffix(".git")
                        
                        if (p, ou) not in gmm_child_map:
                            all_aligned = False
                            break
                        
                        # 仅在子模块，或者指定了具体 tag/commit 的 pip 依赖上校验 commit 哈希是否一致
                        is_submodule = (边.引用类型 == "子模块")
                        ref = 边.额外信息.get("分支", "")
                        is_pinned_pip = (边.引用类型 == "pip依赖" and _is_specific_tag_or_commit(ref))
                        
                        if is_submodule or is_pinned_pip:
                            lock_commit = 边.额外信息.get("锁定commit", "")
                            if gmm_child_map[(p, ou)] != lock_commit:
                                all_aligned = False
                                break
                    
                    if all_aligned:
                        latest_commit = self.上下文.gitee_api.获取最新提交(仓库名)
                        gmm_new_commit = latest_commit.get("sha", "")
                        if gmm_new_commit:
                            self._记录(f"🌟 第一防线校验成功：Gitee 仓库 {仓库名} 的 .gmm_map.json 精准对齐！")
                            return True, gmm_new_commit, child_mappings
        except Exception as e:
            self._记录(f"第一防线校验时发生异常（退化至第二防线）：{str(e)}")

        # 第二防线：扫描最近 100 条提交记录，进行提交消息比对
        try:
            commits = self.上下文.gitee_api.获取历史提交列表(仓库名, 100)
            预期依赖的原始urls = {边.url.rstrip("/").removesuffix(".git") for 边 in 预期依赖列表}
            
            for c in commits:
                msg = c["message"]
                sha = c["sha"]
                match_ok, parsed_orig, parsed_mappings = self._解析提交信息(msg)
                
                if match_ok and parsed_orig == 预期原始commit:
                    all_keys_match = True
                    clean_parsed_keys = {k.rstrip("/").removesuffix(".git") for k in parsed_mappings.keys()}
                    
                    for ou in 预期依赖的原始urls:
                        if ou not in clean_parsed_keys:
                            all_keys_match = False
                            break
                    
                    if all_keys_match:
                        self._记录(f"🌟 第二防线校验成功：Gitee 仓库 {仓库名} 的历史提交消息精准对齐！")
                        return True, sha, parsed_mappings
        except Exception as e:
            self._记录(f"第二防线校验时发生异常：{str(e)}")

        return False, "", {}

    def _步骤_持久化映射文件(self):
        """
        在仓库根目录下持久化生成 .gmm_map.json 文件，记录本仓库与子模块的源/目标映射，并 git add
        """
        if self.上下文.dry_run:
            return
        
        from lib.git_command import Git工具
        if not os.path.isdir(self.本地路径):
            return
            
        子依赖列表 = []
        for 任务 in self.子任务列表:
            子依赖列表.append({
                "名称": 任务.子模块快照.get("名称", "") if 任务.子模块快照 else 任务.仓库名,
                "路径": 任务.子模块快照.get("路径", "") if 任务.子模块快照 else os.path.join("submodules", 任务.仓库名),
                "原始url": 任务.url,
                "新url": 任务.新url or f"https://gitee.com/{self.上下文.gitee用户名}/{任务.仓库名}.git",
                "原始commit": 任务.原始commit,
                "新commit": 任务.新commit or 任务.锁定commit
            })
            
        自身新url = self.新url or f"https://gitee.com/{self.上下文.gitee用户名}/{self.仓库名}.git"
        gmm_data = {
            "原始url": self.url,
            "新url": 自身新url,
            "原始commit": self.原始commit,
            "新commit": self.新commit or "",
            "子依赖列表": 子依赖列表
        }
        
        map_file = os.path.join(self.本地路径, ".gmm_map.json")
        try:
            import json
            with open(map_file, "w", encoding="utf-8") as f:
                json.dump(gmm_data, f, ensure_ascii=False, indent=2)
            
            仓库实例 = Git工具(self.本地路径)
            仓库实例.repo.git.add(".gmm_map.json")
            self._记录("成功在根目录持久化 .gmm_map.json 元数据文件并加入暂存区。")
        except Exception as e:
            self._记录(f"⚠ 持久化元数据文件 .gmm_map.json 失败：{str(e)}")

    # ── 步骤实现 ─────────────────────────────────────────────
    def _步骤_checkout锁定commit(self):
        """checkout 到父级锁定的 commit（detached HEAD）"""
        from lib.git_command import Git工具
        仓库实例 = Git工具(self.本地路径)
        结果 = 仓库实例.checkout(self.锁定commit, 强制=True)
        if not 结果.状态:
            raise RuntimeError(f"checkout 失败：{结果.错误信息}")
        self._记录(f"已 checkout 到锁定 commit：{self.锁定commit[:8]}")

    def _步骤_记录新commit(self):
        """取当前 HEAD hash 作为迁移后 commit"""
        from lib.git_command import Git工具
        if self.上下文.dry_run or not os.path.isdir(self.本地路径):
            return
        仓库实例 = Git工具(self.本地路径)
        结果 = 仓库实例.获取HEAD()
        if 结果.状态:
            self.新commit = 结果.数据
            self._记录(f"迁移后 commit：{self.新commit[:8]}")

    def _步骤_写入缓存(self):
        """把本次迁移结果追加到处理缓存"""
        if self.上下文.dry_run or not self.上下文.处理缓存:
            return
        self.上下文.处理缓存.追加记录(
            旧url=self.url,
            新url=self.新url,
            原始commit=self.原始commit or "",
            迁移后commit=self.新commit or "",
            子模块快照=self.子模块快照,
        )
    def _步骤_克隆(self):
        """克隆远程仓库到缓存目录（如果已存在则跳过并强制重置清除脏数据）"""
        from lib.git_command import Git工具

        if os.path.isdir(self.本地路径) and os.path.exists(os.path.join(self.本地路径, ".git")):
            self._记录(f"本地缓存已存在，复用并强制重置清除上一次改写脏数据：{self.本地路径}")
            if not self.上下文.dry_run:
                try:
                    仓库实例 = Git工具(self.本地路径)
                    # 1. 强行拉取最新的远程状态
                    仓库实例.repo.git.fetch("origin")
                    # 2. 强行丢弃所有本地提交和改写，重置回远程对应的当前分支
                    try:
                        active_branch = 仓库实例.repo.active_branch.name
                        仓库实例.repo.git.reset("--hard", f"origin/{active_branch}")
                    except Exception:
                        仓库实例.repo.git.reset("--hard", "origin/HEAD")
                    # 3. 清理所有残留的工作区脏文件
                    仓库实例.repo.git.clean("-fdx")
                except Exception as re:
                    self._记录(f"  ⚠ 本地缓存重置失败（可能包含脏历史），将重新克隆：{str(re)}")
                    shutil.rmtree(self.本地路径, onerror=解决win权限问题)
                    结果 = Git工具.clone(self.url, self.本地路径)
                    if not 结果.状态:
                        raise RuntimeError(f"克隆失败：{结果.错误信息}")
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
        from lib.git_command import Git工具
        try:
            仓库实例 = Git工具(self.本地路径)
            子模块结果 = 仓库实例.获取子模块列表()
            if 子模块结果.状态 and 子模块结果.数据:
                子模块映射 = {s["URL"].rstrip("/").removesuffix(".git"): s["锁定的提交哈希"] for s in 子模块结果.数据}
                for 边 in 依赖列表:
                    if 边.引用类型 == "子模块":
                        norm_url = 边.url.rstrip("/").removesuffix(".git")
                        if norm_url in 子模块映射:
                            边.额外信息["锁定commit"] = 子模块映射[norm_url]
        except Exception as e:
            self._记录(f"读取子模块锁定提交失败，跳过：{str(e)}")

        for 边 in 依赖列表:
            if 边.引用类型 == "pip依赖":
                ref = 边.额外信息.get("分支", "")
                if ref and _is_specific_tag_or_commit(ref):
                    边.额外信息["锁定commit"] = ref

        return 依赖列表

    def _步骤_递归处理子依赖(self, 依赖列表: list[依赖边]):
        """对每个依赖创建子任务并执行（独立克隆，不走 submodule init）"""
        for 边 in 依赖列表:
            # 判断该依赖是否已经在目标平台（Gitee）
            is_target = 检查引用是否已指向目标(边.url, self.上下文.白名单域名)
            
            # 如果是 Gitee URL，我们需要溯源出其原始 GitHub URL，以便校验其完整性
            if is_target:
                边_仓库名 = 边.url.split("/")[-1].removesuffix(".git")
                原始url = self._尝试获取原始url(边_仓库名, 边.url)
                if not 原始url:
                    self._记录(f"  ⚠ 无法查找到 Gitee 依赖的原始 GitHub URL，尝试拼接默认值：{边.url}")
                    原始url = f"https://github.com/mrnfqrbl/{边_仓库名}.git"
            else:
                边_仓库名 = ""
                原始url = 边.url

            clean_url = 原始url.rstrip("/")
            
            # 检查注册表（去重）
            if clean_url in self.上下文.注册表:
                已有任务 = self.上下文.注册表[clean_url]
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
            子快照 = {"名称": 边.仓库名, "路径": 边.路径, "追踪分支": 边.额外信息.get("追踪分支", "")} if 边.引用类型 == "子模块" else None
            锁定_commit = 边.额外信息.get("锁定commit", "")

            子任务 = 仓库迁移任务(
                url=原始url,
                上下文=self.上下文,
                父任务=self,
                锁定commit=锁定_commit,
                子模块快照=子快照,
                重写仓库名=边_仓库名 if is_target else ""
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
        # 1. 提前推断本仓库未来的新 Gitee URL 并构建包含自引用的合并映射表
        自身新url = f"https://gitee.com/{self.上下文.gitee用户名}/{self.仓库名}.git"
        合并映射表 = dict(self.上下文.映射表)

        # 兼容处理带与不带 .git 后缀的自身旧 URL 映射
        干净自身url = self.url.rstrip("/")
        if 干净自身url.endswith(".git"):
            无后缀自身url = 干净自身url.removesuffix(".git")
            带后缀自身url = 干净自身url
        else:
            无后缀自身url = 干净自身url
            带后缀自身url = 干净自身url + ".git"

        合并映射表[无后缀自身url] = 自身新url
        合并映射表[带后缀自身url] = 自身新url

        if not 合并映射表:
            self._记录("无需改写（合并映射表为空）")
            return

        if self.上下文.dry_run and not os.path.isdir(self.本地路径):
            self._记录("[dry-run] 跳过改写")
            return

        # 步骤 1：git 级别替换（使用合并映射表，支持自引用）
        self._处理子模块替换(合并映射表)

        # 步骤 2：文本兜底改写所有引用载体文件（使用合并映射表，支持自引用）
        改动 = 改写所有引用(self.本地路径, 合并映射表)
        if 改动:
            for 条目 in 改动:
                self._记录(f"  改写：{条目}")
        else:
            self._记录("引用文件中无需文本改写的匹配项")

        # 将所有已成功处理/记录新url的子任务（包含子模块和pip依赖）合并映射关系，全部加入 self.替换对
        # 从而在提交的 commit message 里完整记录所有依赖映射关系，便于第二防线精确校验
        for 任务 in self.子任务列表:
            if 任务.url not in self.替换对:
                self.替换对[任务.url] = 任务.新url or f"https://gitee.com/{self.上下文.gitee用户名}/{任务.仓库名}.git"

    def _处理子模块替换(self, 映射表: dict):
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
            is_target_url = 检查引用是否已指向目标(旧url, self.上下文.白名单域名)
            
            if not is_target_url and 旧url not in 映射表:
                continue

            新url = 映射表.get(旧url, 旧url)
            名称 = 子模块["名称"]
            路径 = 子模块["路径"]
            分支 = 子模块.get("追踪分支", None)

            # 获取子模块应指向的正确提交（新迁移的 commit 或者是原锁定 commit）
            对应任务 = self.上下文.注册表.get(旧url)
            目标commit = None
            if 对应任务:
                目标commit = 对应任务.新commit or 对应任务.锁定commit
            if not 目标commit:
                目标commit = 子模块.get("锁定的提交哈希", None)

            # 如果新url与旧url完全一致且已经指向 Gitee，则只更新并检出提交指针，免去删除和重建的开销
            if is_target_url and 新url.rstrip("/").removesuffix(".git") == 旧url.rstrip("/").removesuffix(".git"):
                if 目标commit:
                    try:
                        # 1. 尝试直接通过本地路径打开子仓库（避开 GitPython 内部对 submodule 列表的缓存/中文路径 Bug）
                        sub_repo_path = os.path.join(仓库实例.repo.working_tree_dir, 路径)
                        sub_repo = None
                        if os.path.exists(os.path.join(sub_repo_path, ".git")):
                            try:
                                sub_repo = git.Repo(sub_repo_path)
                            except Exception:
                                pass
                        
                        if not sub_repo:
                            new_submodule = 仓库实例.repo.submodule(名称)
                            new_submodule.update(init=True, force=True)
                            sub_repo = new_submodule.module()

                        try:
                            sub_repo.git.fetch()
                        except Exception as fe:
                            self._记录(f"  ⚠ 子模块 fetch 失败：{str(fe)}")
                        sub_repo.git.checkout(目标commit, force=True)
                        仓库实例.repo.git.add(路径)
                        self._记录(f"  成功将已存在的 Gitee 子模块 {名称} 指针更新至 commit: {目标commit}")
                    except Exception as e:
                        self._记录(f"  ⚠ 更新 Gitee 子模块 {名称} 指针至 commit {目标commit} 失败：{str(e)}")
                continue

            self._记录(f"  替换子模块：{名称} → {新url}，目标 commit：{目标commit}")

            # 删除旧子模块
            删除结果 = 仓库实例.删除子模块(名称)
            if not 删除结果.状态:
                self._记录(f"  ⚠ 删除子模块失败：{删除结果.错误信息}，跳过")
                continue

            # 重新添加新 URL 子模块
            添加结果 = 仓库实例.添加子模块(名称, 路径, 新url, 分支=分支)
            if not 添加结果.状态:
                self._记录(f"  ⚠ 添加子模块失败：{添加结果.错误信息}")
                continue

            # 成功添加，记录到替换对中
            self.替换对[旧url] = 新url

            # 检出到对应的同一个提交或修改后的新提交，并 add 到父仓库
            if 目标commit:
                try:
                    # 1. 尝试直接通过本地路径打开子仓库（避开 GitPython 内部对 submodule 列表的缓存/中文路径 Bug）
                    sub_repo_path = os.path.join(仓库实例.repo.working_tree_dir, 路径)
                    sub_repo = None
                    if os.path.exists(os.path.join(sub_repo_path, ".git")):
                        try:
                            sub_repo = git.Repo(sub_repo_path)
                        except Exception:
                            pass
                    
                    if not sub_repo:
                        # 强制清除 GitPython 内部对 submodules 列表的缓存
                        if hasattr(仓库实例.repo, "_submodules"):
                            try:
                                del 仓库实例.repo._submodules
                            except Exception:
                                pass
                        new_submodule = 仓库实例.repo.submodule(名称)
                        new_submodule.update(init=True, force=True)
                        sub_repo = new_submodule.module()

                    # 确保本地已拉取最新的 commit (解决分布式目录缓存的 tree 找不到问题)
                    try:
                        sub_repo.git.fetch()
                    except Exception as fe:
                        self._记录(f"  ⚠ 子模块 fetch 失败（将尝试直接checkout）：{str(fe)}")
                    sub_repo.git.checkout(目标commit, force=True)
                    仓库实例.repo.git.add(路径)
                    self._记录(f"  成功将新子模块 {名称} 检出至 commit: {目标commit}")
                except Exception as e:
                    self._记录(f"  ⚠ 检出新子模块 {名称} 到 commit {目标commit} 失败：{str(e)}")

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

        # 在提交前，强制先写入持久化映射元数据文件
        self._步骤_持久化映射文件()

        仓库实例 = Git工具(self.本地路径)

        # 检查是否有变更需要提交
        脏检查 = 仓库实例.是否有未提交更改()
        if not 脏检查.状态 or not 脏检查.数据:
            self._记录("无变更需要提交")
            return

        # 构造高可读性且结构化的提交消息
        msg_lines = [
            "[git_modules_mg] 迁移引用至 gitee",
            f"原始commit: {self.原始commit or ''}"
        ]
        if self.替换对:
            msg_lines.append("依赖映射:")
            for k, v in self.替换对.items():
                msg_lines.append(f"- {k} -> {v}")
        
        提交信息 = "\n".join(msg_lines)

        提交结果 = 仓库实例.提交(
            提交信息=提交信息,
            是否允许自动add=True
        )
        if 提交结果.状态:
            self._记录(f"提交成功：{提交结果.数据}")
        else:
            self._记录(f"⚠ 提交失败：{提交结果.错误信息}")

    def _步骤_推送到gitee(self):
        """确保 gitee 上仓库存在 → 添加 remote → 强制推送"""
        from lib.git_command import Git工具

        # 确保 gitee 仓库存在
        self._确保gitee仓库存在()

        # 构造目标 URL
        目标url = f"https://gitee.com/{self.上下文.gitee用户名}/{self.仓库名}.git"
        self.新url = 目标url

        if self.上下文.dry_run:
            self._记录(f"[dry-run] 目标URL：{目标url}")
            return

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

        # 强制推送所有分支 and tags
        self._记录(f"推送到 gitee：{目标url}")
        try:
            # 1. 强制推送所有已存在的本地分支
            仓库实例.repo.git.push("gitee", "--all", "--force")
            
            # 2. 强制推送当前 HEAD 到已记录的默认活跃分支上，确保无论是否处于 detached HEAD，新生成的提交均会被作为最新 HEAD 推送
            if self.默认分支:
                self._记录(f"  强制推送当前 HEAD 提交到远程分支: {self.默认分支}")
                仓库实例.repo.git.push("gitee", f"HEAD:{self.默认分支}", "--force")
            
            # 3. 推送所有 tags
            仓库实例.repo.git.push("gitee", "--tags", "--force")
            self._记录("推送成功（全部分支 + tags）")
        except Exception as e:
            # 退化：只推送当前 HEAD 到默认分支
            self._记录(f"⚠ 全量推送失败，尝试将 HEAD 推送到默认分支 {self.默认分支}：{str(e)}")
            try:
                仓库实例.repo.git.push("gitee", f"HEAD:{self.默认分支}", "--force")
            except Exception as e2:
                raise RuntimeError(f"推送失败：{str(e2)}")

    def _更新gitee仓库属性(self):
        if self.上下文.dry_run or self.上下文.no_push:
            return
        try:
            self._记录(f"设置 Gitee 仓库 {self.仓库名} 的属性为：{'公开' if self.上下文.public else '私有'}")
            self.上下文.gitee_api.修改仓库属性(self.仓库名, 私有=not self.上下文.public)
        except Exception as e:
            self._记录(f"  ⚠ 修改仓库属性异常：{str(e)}")

    def _确保gitee仓库存在(self):
        """确保 Gitee 仓库存在。如果已有属于本仓库的镜像，直接复用其名称。否则查找空闲顺位名称并创建之。"""
        # 1. 寻找已有的属于当前源仓库的镜像（例如 test2_1）
        已有镜像名 = self._寻找已有的本仓库镜像()
        if 已有镜像名:
            self._记录(f"发现已有的本仓库 Gitee 镜像：{self.仓库名} → {已有镜像名}")
            self.仓库名 = 已有镜像名
            self._更新gitee仓库属性()
            return

        # 2. 没有镜像时，按顺序查找第一个真正不可被任何用户占用的空闲顺位名称
        连续不存在次数 = 0
        最大连续不存在 = 3
        最大尝试 = 50
        候选名称列表 = [self.仓库名] + [f"{self.仓库名}_{i}" for i in range(1, 最大尝试 + 1)]
        
        for name in 候选名称列表:
            if not self.上下文.gitee_api.仓库是否存在(name):
                self._记录(f"使用空闲的 Gitee 仓库名：{self.仓库名} → {name}")
                self.仓库名 = name
                self._创建gitee仓库()
                return

        raise RuntimeError(f"在 {最大尝试} 次尝试内未找到可用的 Gitee 仓库名")

    def _创建gitee仓库(self):
        self._记录(f"创建 Gitee 仓库：{self.仓库名}")
        try:
            self.上下文.gitee_api.创建仓库(self.仓库名, 描述=f"镜像自 {self.url}", 私有=not self.上下文.public)
            self._记录(f"创建成功")
        except Exception as e:
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
    处理缓存实例: 处理缓存 = None,
    dry_run: bool = False,
    logger=None,
    no_push: bool = False,
    public: bool = True,
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
    :param public: 是否公开仓库
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
        处理缓存实例=处理缓存实例,
        no_push=no_push,
        public=public,
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
