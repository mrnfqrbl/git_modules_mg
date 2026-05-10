#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git仓库迁移引擎
支持递归子仓库和依赖迁移的完整流水线处理系统
"""

import os
import re
import json
import shutil
import toml
import git
from git import Repo, GitCommandError
from typing import Dict, Any, List, Optional, Set, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

from lib.git_base_api import GitBaseApi, GiteeApi
from lib.git_command import Git工具


# ====================== 【枚举定义】 ======================
class 任务状态枚举(Enum):
    """任务状态枚举"""
    待处理 = "待处理"
    处理中 = "处理中"
    已完成 = "已完成"
    失败 = "失败"
    跳过 = "跳过"


class 任务类型枚举(Enum):
    """任务类型枚举"""
    子仓库 = "子仓库"
    依赖 = "依赖"
    一级仓库 = "一级仓库"




# ====================== 【递归任务类】 ======================
@dataclass
class 递归任务类:
    """
    递归子仓库/依赖任务类
    用于嵌套处理子仓库的子仓库和依赖
    构建溯源和处理状态的流转对象
    """
    # 基础信息
    任务ID: str
    任务类型: 任务类型枚举
    原始仓库URL: str
    本地路径: str
    层级: int = 1

    # 状态信息
    状态: 任务状态枚举 = 任务状态枚举.待处理
    处理开始时间: Optional[datetime] = None
    处理结束时间: Optional[datetime] = None
    错误信息: Optional[str] = None

    # 迁移信息
    新仓库名称: str = ""
    新仓库URL: str = ""
    新仓库SSH地址: str = ""

    # 溯源信息
    父任务ID: Optional[str] = None
    子任务列表: List["递归任务类"] = field(default_factory=list)
    依赖任务列表: List["递归任务类"] = field(default_factory=list)

    # 处理记录
    处理日志: List[Dict[str, Any]] = field(default_factory=list)

    def 添加处理日志(self, 操作: str, 详情: str, 成功: bool = True):
        """添加处理日志"""
        self.处理日志.append({
            "时间": datetime.now().isoformat(),
            "操作": 操作,
            "详情": 详情,
            "成功": 成功
        })

    def 开始处理(self):
        """标记开始处理"""
        self.状态 = 任务状态枚举.处理中
        self.处理开始时间 = datetime.now()
        self.添加处理日志("开始处理", f"开始处理{self.任务类型.value}")

    def 完成处理(self):
        """标记处理完成"""
        self.状态 = 任务状态枚举.已完成
        self.处理结束时间 = datetime.now()
        self.添加处理日志("处理完成", f"{self.任务类型.value}处理完成")

    def 处理失败(self, 错误信息: str):
        """标记处理失败"""
        self.状态 = 任务状态枚举.失败
        self.处理结束时间 = datetime.now()
        self.错误信息 = 错误信息
        self.添加处理日志("处理失败", 错误信息, 成功=False)

    def 获取所有后代任务(self) -> List["递归任务类"]:
        """获取所有后代任务（递归）"""
        所有任务 = []
        for 子任务 in self.子任务列表:
            所有任务.append(子任务)
            所有任务.extend(子任务.获取所有后代任务())
        for 依赖任务 in self.依赖任务列表:
            所有任务.append(依赖任务)
            所有任务.extend(依赖任务.获取所有后代任务())
        return 所有任务

    def 获取最大层级(self) -> int:
        """获取当前任务树的最大层级"""
        当前最大 = self.层级
        for 子任务 in self.子任务列表 + self.依赖任务列表:
            当前最大 = max(当前最大, 子任务.获取最大层级())
        return 当前最大

    def 按层级获取任务(self, 目标层级: int) -> List["递归任务类"]:
        """按层级获取任务"""
        任务列表 = []
        if self.层级 == 目标层级:
            任务列表.append(self)
        for 子任务 in self.子任务列表 + self.依赖任务列表:
            任务列表.extend(子任务.按层级获取任务(目标层级))
        return 任务列表

    def 生成溯源报告(self) -> Dict[str, Any]:
        """生成溯源报告"""
        return {
            "任务ID": self.任务ID,
            "任务类型": self.任务类型.value,
            "原始仓库URL": self.原始仓库URL,
            "新仓库URL": self.新仓库URL,
            "层级": self.层级,
            "状态": self.状态.value,
            "错误信息": self.错误信息,
            "处理日志数量": len(self.处理日志),
            "子任务数量": len(self.子任务列表),
            "依赖任务数量": len(self.依赖任务列表),
            "子任务溯源": [t.生成溯源报告() for t in self.子任务列表],
            "依赖任务溯源": [t.生成溯源报告() for t in self.依赖任务列表]
        }


# ====================== 【一级仓库任务类】 ======================
@dataclass
class 一级仓库任务类:
    """
    一级子仓库任务类
    包含嵌套的递归任务类，用于处理顶级仓库下的每个一级子仓库
    """
    # 基础信息
    任务ID: str
    子仓库名称: str
    子仓库相对路径: str
    原始仓库URL: str
    子仓库分支: str
    顶级仓库路径: str

    # 本地路径
    本地缓存路径: str = ""

    # 状态信息
    状态: 任务状态枚举 = 任务状态枚举.待处理
    处理开始时间: Optional[datetime] = None
    处理结束时间: Optional[datetime] = None
    错误信息: Optional[str] = None

    # 迁移信息
    新仓库名称: str = ""
    新仓库URL: str = ""
    新仓库SSH地址: str = ""

    # 嵌套递归任务
    递归根任务: Optional[递归任务类] = None

    # 处理记录
    处理日志: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        """初始化后处理"""
        if not self.本地缓存路径:
            self.本地缓存路径 = os.path.join(os.path.dirname(self.顶级仓库路径), "migration_cache", self.子仓库名称)

    def 添加处理日志(self, 操作: str, 详情: str, 成功: bool = True):
        """添加处理日志"""
        self.处理日志.append({
            "时间": datetime.now().isoformat(),
            "操作": 操作,
            "详情": 详情,
            "成功": 成功
        })

    def 开始处理(self):
        """标记开始处理"""
        self.状态 = 任务状态枚举.处理中
        self.处理开始时间 = datetime.now()
        self.添加处理日志("开始处理", f"开始处理一级子仓库：{self.子仓库名称}")

    def 完成处理(self):
        """标记处理完成"""
        self.状态 = 任务状态枚举.已完成
        self.处理结束时间 = datetime.now()
        self.添加处理日志("处理完成", f"一级子仓库处理完成：{self.子仓库名称}")

    def 处理失败(self, 错误信息: str):
        """标记处理失败"""
        self.状态 = 任务状态枚举.失败
        self.处理结束时间 = datetime.now()
        self.错误信息 = 错误信息
        self.添加处理日志("处理失败", 错误信息, 成功=False)

    def 获取所有递归任务(self) -> List[递归任务类]:
        """获取所有递归任务"""
        if not self.递归根任务:
            return []
        return [self.递归根任务] + self.递归根任务.获取所有后代任务()

    def 获取最大层级(self) -> int:
        """获取任务树的最大层级"""
        if not self.递归根任务:
            return 1
        return self.递归根任务.获取最大层级()

    def 按层级获取任务(self, 目标层级: int) -> List[递归任务类]:
        """按层级获取任务"""
        if not self.递归根任务:
            return []
        return self.递归根任务.按层级获取任务(目标层级)

    def 生成完整溯源报告(self) -> Dict[str, Any]:
        """生成完整溯源报告"""
        return {
            "任务ID": self.任务ID,
            "子仓库名称": self.子仓库名称,
            "原始仓库URL": self.原始仓库URL,
            "新仓库URL": self.新仓库URL,
            "状态": self.状态.value,
            "错误信息": self.错误信息,
            "处理日志数量": len(self.处理日志),
            "最大层级": self.获取最大层级(),
            "递归任务溯源": self.递归根任务.生成溯源报告() if self.递归根任务 else None,
            "处理日志": self.处理日志
        }

#TODO: 主迁移逻辑为，克隆-递归拉取-最底层提交-修改-1层引用以此类推直到一级子仓库提交并推送
#TODO: 子仓库逻辑和迁移逻辑独立，直接使用迁移后目标作为子仓库添加来源

# ====================== 【迁移引擎核心类】 ======================
class 迁移引擎:
    """
    Git仓库迁移引擎
    实现完整的流水线处理模型：
    1. 拉取一级子仓库
    2. 递归拉取递归子仓库和依赖（从1到n层）
    3. 从n层到第1层反向处理
    4. 处理所有一级子仓库
    5. 在顶级仓库中添加一级子仓库
    6. 审查溯源记录
    """

    def __init__(self, api: GitBaseApi, git工具: Git工具, 缓存目录: str):
        self.api = api
        self.git工具 = git工具
        self.缓存目录 = 缓存目录
        self.顶级仓库路径 = ""
        self.一级任务列表: List[一级仓库任务类] = []
        self.任务计数器 = 0

        # 确保缓存目录存在
        os.makedirs(self.缓存目录, exist_ok=True)

    def 生成任务ID(self) -> str:
        """生成唯一任务ID"""
        self.任务计数器 += 1
        return f"TASK-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self.任务计数器:04d}"

    def 提取仓库名称(self, 仓库URL: str) -> str:
        """从仓库URL中提取仓库名称"""
        # 处理各种URL格式
        # https://github.com/user/repo.git
        # git@github.com:user/repo.git
        # https://gitee.com/user/repo
        名称 = 仓库URL.split("/")[-1]
        if 名称.endswith(".git"):
            名称 = 名称[:-4]
        return 名称

    def 迁移仓库(self, 顶级仓库路径: str):
        """
        完整的仓库迁移流程入口
        流水线处理模型的主入口
        """
        print(f"\n{'='*60}")
        print(f"🚀 开始仓库迁移流程：{顶级仓库路径}")
        print(f"{'='*60}\n")

        # 步骤1：克隆顶级仓库
        print("📦 步骤1：克隆顶级仓库")
        self.顶级仓库路径 = 顶级仓库路径

        #从顶级仓库目录中导入modules_cfg.py 中的一级子仓库配置
        一级子仓库配置 = self.导入一级子仓库配置(os.path.join(self.顶级仓库路径, "module_cfg.py"))


        # 步骤2：检测并构建一级子仓库任务
        print("\n🔍 步骤2：检测并构建一级子仓库任务")
        self.构建一级子仓库任务(一级子仓库配置)

        if not self.一级任务列表:
            print("ℹ️ 未检测到一级子仓库，迁移流程结束")
            return

        print(f"✅ 检测到 {len(self.一级任务列表)} 个一级子仓库")

        # 步骤3：处理每个一级子仓库（核心流水线）
        print("\n⚙️ 步骤3：处理每个一级子仓库（核心流水线）")
        for 索引, 一级任务 in enumerate(self.一级任务列表, 1):
            print(f"\n{'─'*50}")
            print(f"处理一级子仓库 [{索引}/{len(self.一级任务列表)}]：{一级任务.子仓库名称}")
            print(f"{'─'*50}")
            self.处理单个一级子仓库(一级任务)

        # 步骤4：在顶级仓库中添加处理完成的一级子仓库
        print("\n📝 步骤4：在顶级仓库中更新一级子仓库")
        self.更新顶级仓库子仓库配置()

        # 步骤5：生成并审查溯源报告
        print("\n📊 步骤5：生成并审查溯源报告")
        self.生成并审查溯源报告()

        print(f"\n{'='*60}")
        print(f"✅ 仓库迁移流程完成！")
        print(f"{'='*60}\n")

    def 构建一级子仓库任务(self,一级子仓库配置):
        """检测并构建一级子仓库任务列表"""
        子仓库列表 = 一级子仓库配置

        for 子仓库信息 in 子仓库列表:
            一级任务 = 一级仓库任务类(
                任务ID=self.生成任务ID(),
                子仓库名称=子仓库信息["名称"],
                子仓库相对路径=子仓库信息["路径"],
                原始仓库URL=子仓库信息["URL"],
                子仓库分支=子仓库信息["分支"],
                顶级仓库路径=self.顶级仓库路径
            )
            self.一级任务列表.append(一级任务)
            print(f"  ✅ 构建一级任务：{一级任务.子仓库名称}")

    def 处理单个一级子仓库(self, 一级任务: 一级仓库任务类):
        """
        处理单个一级子仓库（核心流水线）
        流水线：拉取 -> 递归检测 -> 反向处理 -> 推送
        """
        一级任务.开始处理()

        try:
            # 3.1 拉取一级子仓库
            print("  📥 3.1 拉取一级子仓库")
            if 一级任务.子仓库分支:
                拉库结果= self.git工具.克隆远程仓库(一级任务.原始仓库URL, 一级任务.本地缓存路径, 分支=一级任务.子仓库分支)
            else:
                拉库结果= self.git工具.克隆远程仓库(一级任务.原始仓库URL, 一级任务.本地缓存路径)
            if not 拉库结果:
                一级任务.处理失败(f"克隆一级子仓库失败：{一级任务.原始仓库URL}")
                return

            # 3.2 递归检测子仓库和依赖（构建任务树 - 从1到n层）
            print("  🔍 3.2 递归检测子仓库和依赖（构建任务树）")
            一级任务.递归根任务 = 递归任务类(
                任务ID=self.生成任务ID(),
                任务类型=任务类型枚举.子仓库,
                原始仓库URL=一级任务.原始仓库URL,
                本地路径=一级任务.本地缓存路径,
                层级=1,
                父任务ID=一级任务.任务ID
            )
            self.递归检测并构建任务树(一级任务.递归根任务)

            最大层级 = 一级任务.获取最大层级()
            print(f"  ✅ 任务树构建完成，最大层级：{最大层级}")

            # 3.3 从n层到第1层反向处理
            print(f"  🔄 3.3 从第{最大层级}层到第1层反向处理")
            for 当前层级 in range(最大层级, 0, -1):
                print(f"    📍 处理第{当前层级}层任务")
                当前层级任务 = 一级任务.按层级获取任务(当前层级)
                for 任务 in 当前层级任务:
                    self.处理单个递归任务(任务)

            # 3.4 创建并推送一级子仓库到Gitee
            print("  ☁️ 3.4 创建并推送一级子仓库到Gitee")
            self.创建并推送仓库到Gitee(一级任务)

            一级任务.完成处理()
            print(f"  ✅ 一级子仓库处理完成：{一级任务.子仓库名称}")

        except Exception as e:
            错误信息 = str(e)
            一级任务.处理失败(错误信息)
            print(f"  ❌ 一级子仓库处理失败：{错误信息}")

    def 递归检测并构建任务树(self, 当前任务: 递归任务类):
        """
        递归检测子仓库和依赖，构建任务树
        从1层到n层深度优先构建
        """
        当前任务.添加处理日志("递归检测", f"开始检测路径：{当前任务.本地路径}")

        # 检测子仓库
        子仓库列表 = self.递归检测子仓库(当前任务.本地路径)
        for 子仓库信息 in 子仓库列表:
            子任务 = 递归任务类(
                任务ID=self.生成任务ID(),
                任务类型=任务类型枚举.子仓库,
                原始仓库URL=子仓库信息["URL"],
                本地路径=os.path.join(当前任务.本地路径, 子仓库信息["路径"]),
                层级=当前任务.层级 + 1,
                父任务ID=当前任务.任务ID
            )
            当前任务.子任务列表.append(子任务)
            print(f"      发现子仓库（第{子任务.层级}层）：{子仓库信息['名称']}")

            # 递归处理子任务
            if not os.path.exists(子任务.本地路径):
                self.git工具.克隆远程仓库(子任务.原始仓库URL, 子任务.本地路径)
            self.递归检测并构建任务树(子任务)

        # 检测依赖
        依赖列表 = self.递归检测仓库依赖(当前任务.本地路径)
        for 依赖信息 in 依赖列表:
            依赖任务 = 递归任务类(
                任务ID=self.生成任务ID(),
                任务类型=任务类型枚举.依赖,
                原始仓库URL=依赖信息["URL"],
                本地路径=os.path.join(self.缓存目录, "deps", self.提取仓库名称(依赖信息["URL"])),
                层级=当前任务.层级 + 1,
                父任务ID=当前任务.任务ID
            )
            当前任务.依赖任务列表.append(依赖任务)
            print(f"      发现Git依赖（第{依赖任务.层级}层）：{self.提取仓库名称(依赖信息['URL'])}")

            # 递归处理依赖任务
            if not os.path.exists(依赖任务.本地路径):
                self.git工具.克隆远程仓库(依赖任务.原始仓库URL, 依赖任务.本地路径)
            self.递归检测并构建任务树(依赖任务)

    def 递归检测子仓库(self, 仓库路径: str) -> List[Dict[str, str]]:
        """读取仓库子仓库配置信息并递归检测"""
        return self.git工具.获取子仓库列表(仓库路径)

    def 递归检测仓库依赖(self, 仓库路径: str) -> List[Dict[str, str]]:
        """
        读取仓库依赖配置信息并递归检测
        支持：requirements.txt 和 pyproject.toml
        检测其中的 git+ 形式的依赖
        """
        依赖列表 = []
        已检测URL: Set[str] = set()

        # 检测 requirements.txt
        requirements_path = os.path.join(仓库路径, "requirements.txt")
        if os.path.exists(requirements_path):
            try:
                with open(requirements_path, 'r', encoding='utf-8') as f:
                    内容 = f.read()

                # 匹配 git+ 开头的依赖
                git_pattern = r'git\+(https?://[^\s]+)'
                匹配结果 = re.findall(git_pattern, 内容)
                for url in 匹配结果:
                    if url not in 已检测URL:
                        已检测URL.add(url)
                        依赖列表.append({
                            "URL": url,
                            "来源": "requirements.txt",
                            "类型": "git+https"
                        })
            except Exception as e:
                print(f"      ⚠️  读取requirements.txt失败：{str(e)}")

        # 检测 pyproject.toml
        pyproject_path = os.path.join(仓库路径, "pyproject.toml")
        if os.path.exists(pyproject_path):
            try:
                with open(pyproject_path, 'r', encoding='utf-8') as f:
                    配置 = toml.load(f)

                # 检查 dependencies
                if "project" in 配置 and "dependencies" in 配置["project"]:
                    for 依赖 in 配置["project"]["dependencies"]:
                        if 依赖.startswith("git+"):
                            url = 依赖[4:]  # 去掉 git+ 前缀
                            if url not in 已检测URL:
                                已检测URL.add(url)
                                依赖列表.append({
                                    "URL": url,
                                    "来源": "pyproject.toml[dependencies]",
                                    "类型": "git+https"
                                })

                # 检查 [tool.poetry.dependencies]
                if "tool" in 配置 and "poetry" in 配置["tool"] and "dependencies" in 配置["tool"]["poetry"]:
                    for 包名, 版本信息 in 配置["tool"]["poetry"]["dependencies"].items():
                        if isinstance(版本信息, dict) and "git" in 版本信息:
                            url = 版本信息["git"]
                            if url not in 已检测URL:
                                已检测URL.add(url)
                                依赖列表.append({
                                    "URL": url,
                                    "来源": f"pyproject.toml[poetry.dependencies.{包名}]",
                                    "类型": "poetry-git"
                                })
            except Exception as e:
                print(f"      ⚠️  读取pyproject.toml失败：{str(e)}")

        return 依赖列表

    def 处理单个递归任务(self, 任务: 递归任务类):
        """处理单个递归任务（子仓库或依赖）"""
        if 任务.状态 != 任务状态枚举.待处理:
            return

        任务.开始处理()

        try:
            # 1. 创建Gitee仓库
            print(f"      ☁️  创建Gitee仓库：{self.提取仓库名称(任务.原始仓库URL)}")
            仓库名称 = self.提取仓库名称(任务.原始仓库URL)

            if not self.api.仓库是否存在(仓库名称):
                创建结果 = self.api.创建仓库(
                    名称=仓库名称,
                    描述=f"Migrated from {任务.原始仓库URL}",
                    私有=True,
                    自动初始化=False
                )
                任务.新仓库名称 = 仓库名称
                任务.新仓库URL = 创建结果["仓库地址"]
                任务.新仓库SSH地址 = 创建结果.get("SSH地址", "")
            else:
                仓库信息 = self.api.获取仓库信息(仓库名称)
                任务.新仓库名称 = 仓库名称
                任务.新仓库URL = 仓库信息["仓库地址"]

            # 2. 关联远程并推送
            print(f"      📤 推送代码到Gitee")
            if self.git工具.是否为有效仓库(任务.本地路径):
                # 先移除已有的origin
                try:
                    repo = Repo(任务.本地路径)
                    if "origin" in [r.name for r in repo.remotes]:
                        repo.delete_remote("origin")
                except:
                    pass

                self.git工具.关联远程仓库(任务.本地路径, 任务.新仓库URL)
                self.git工具.推送本地代码(任务.本地路径)

            # 3. 如果有父任务，更新父任务中的引用
            if 任务.父任务ID:
                print(f"      🔗 更新父任务中的依赖引用")
                # 这里会在父任务处理时统一更新依赖文件

            任务.完成处理()
            print(f"      ✅ 任务处理完成：{任务.任务ID}")

        except Exception as e:
            任务.处理失败(str(e))
            print(f"      ❌ 任务处理失败：{str(e)}")

    def 创建并推送仓库到Gitee(self, 一级任务: 一级仓库任务类):
        """创建并推送一级子仓库到Gitee"""
        try:
            # 1. 更新子仓库配置和依赖文件（使用已迁移的新URL）
            self.更新仓库内的引用(一级任务)

            # 2. 创建Gitee仓库
            仓库名称 = 一级任务.子仓库名称
            if not self.api.仓库是否存在(仓库名称):
                创建结果 = self.api.创建仓库(
                    名称=仓库名称,
                    描述=f"Migrated from {一级任务.原始仓库URL}",
                    私有=True,
                    自动初始化=False
                )
                一级任务.新仓库URL = 创建结果["仓库地址"]
                一级任务.新仓库SSH地址 = 创建结果.get("SSH地址", "")
            else:
                仓库信息 = self.api.获取仓库信息(仓库名称)
                一级任务.新仓库URL = 仓库信息["仓库地址"]

            # 3. 提交所有更改
            self.git工具.添加文件到暂存区(一级任务.本地缓存路径)
            self.git工具.提交更改到仓库(一级任务.本地缓存路径, "chore: 迁移仓库并更新所有依赖引用")

            # 4. 关联远程并推送
            try:
                repo = Repo(一级任务.本地缓存路径)
                if "origin" in [r.name for r in repo.remotes]:
                    repo.delete_remote("origin")
            except:
                pass

            self.git工具.关联远程仓库(一级任务.本地缓存路径, 一级任务.新仓库URL)
            self.git工具.推送本地代码(一级任务.本地缓存路径)

            一级任务.添加处理日志("推送完成", f"成功推送到：{一级任务.新仓库URL}")

        except Exception as e:
            raise Exception(f"创建并推送失败：{str(e)}")

    def 更新仓库内的引用(self, 一级任务: 一级仓库任务类):
        """更新仓库内所有子仓库和依赖的引用"""
        if not 一级任务.递归根任务:
            return

        # 获取所有已迁移的任务的URL映射
        url_mapping = {}
        for 任务 in 一级任务.获取所有递归任务():
            if 任务.新仓库URL:
                url_mapping[任务.原始仓库URL] = 任务.新仓库URL

        # 更新 .gitmodules
        gitmodules_path = os.path.join(一级任务.本地缓存路径, ".gitmodules")
        if os.path.exists(gitmodules_path):
            try:
                with open(gitmodules_path, 'r', encoding='utf-8') as f:
                    内容 = f.read()

                for 原始URL, 新URL in url_mapping.items():
                    内容 = 内容.replace(原始URL, 新URL)

                with open(gitmodules_path, 'w', encoding='utf-8') as f:
                    f.write(内容)

                print(f"    ✅ 更新.gitmodules完成")
            except Exception as e:
                print(f"    ⚠️  更新.gitmodules失败：{str(e)}")

        # 更新 requirements.txt
        requirements_path = os.path.join(一级任务.本地缓存路径, "requirements.txt")
        if os.path.exists(requirements_path):
            try:
                with open(requirements_path, 'r', encoding='utf-8') as f:
                    内容 = f.read()

                for 原始URL, 新URL in url_mapping.items():
                    内容 = 内容.replace(原始URL, 新URL)

                with open(requirements_path, 'w', encoding='utf-8') as f:
                    f.write(内容)

                print(f"    ✅ 更新requirements.txt完成")
            except Exception as e:
                print(f"    ⚠️  更新requirements.txt失败：{str(e)}")

        # 更新 pyproject.toml
        pyproject_path = os.path.join(一级任务.本地缓存路径, "pyproject.toml")
        if os.path.exists(pyproject_path):
            try:
                with open(pyproject_path, 'r', encoding='utf-8') as f:
                    内容 = f.read()

                for 原始URL, 新URL in url_mapping.items():
                    内容 = 内容.replace(原始URL, 新URL)

                with open(pyproject_path, 'w', encoding='utf-8') as f:
                    f.write(内容)

                print(f"    ✅ 更新pyproject.toml完成")
            except Exception as e:
                print(f"    ⚠️  更新pyproject.toml失败：{str(e)}")

    def 更新顶级仓库子仓库配置(self):
        """在顶级仓库中更新一级子仓库配置"""
        print("  更新顶级仓库的子仓库配置...")

        for 一级任务 in self.一级任务列表:
            if 一级任务.状态 != 任务状态枚举.已完成:
                print(f"    ⚠️  跳过失败任务：{一级任务.子仓库名称}")
                continue

            # 规范：凡是涉及子仓库的变更，一律完整删除残留后重新添加
            print(f"    🗑️  删除子仓库：{一级任务.子仓库相对路径}")
            self.git工具.删除子仓库(self.顶级仓库路径, 一级任务.子仓库相对路径)

            # 重新添加子仓库
            print(f"    ➕ 重新添加子仓库：{一级任务.子仓库名称}")
            self.git工具.添加子仓库(
                self.顶级仓库路径,
                一级任务.新仓库URL,
                一级任务.子仓库相对路径
            )

        # 只提交不推送
        self.git工具.添加文件到暂存区(self.顶级仓库路径)
        self.git工具.提交更改到仓库(self.顶级仓库路径, "chore: 迁移所有一级子仓库到Gitee")
        print("  ✅ 顶级仓库子仓库配置更新完成（已提交，未推送）")

    def 生成并审查溯源报告(self):
        """生成并审查溯源记录"""
        报告目录 = os.path.join(self.缓存目录, "reports")
        os.makedirs(报告目录, exist_ok=True)

        完整报告 = {
            "迁移时间": datetime.now().isoformat(),
            "顶级仓库路径": self.顶级仓库路径,
            "一级子仓库总数": len(self.一级任务列表),
            "成功数量": sum(1 for t in self.一级任务列表 if t.状态 == 任务状态枚举.已完成),
            "失败数量": sum(1 for t in self.一级任务列表 if t.状态 == 任务状态枚举.失败),
            "一级任务详情": [t.生成完整溯源报告() for t in self.一级任务列表]
        }

        # 保存报告
        报告路径 = os.path.join(报告目录, f"migration_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
        with open(报告路径, 'w', encoding='utf-8') as f:
            json.dump(完整报告, f, ensure_ascii=False, indent=2)

        # 审查结果
        print(f"\n{'─'*50}")
        print("📋 迁移审查结果：")
        print(f"  一级子仓库总数：{完整报告['一级子仓库总数']}")
        print(f"  成功：{完整报告['成功数量']}")
        print(f"  失败：{完整报告['失败数量']}")
        print(f"  报告已保存：{报告路径}")

        if 完整报告["失败数量"] > 0:
            print("\n⚠️  失败任务列表：")
            for 任务 in self.一级任务列表:
                if 任务.状态 == 任务状态枚举.失败:
                    print(f"  - {任务.子仓库名称}: {任务.错误信息}")

        print(f"{'─'*50}")

    def 导入一级子仓库配置(self, 文件路径: str) -> List[Dict[str, Any]]:
        import importlib.util
        import os
        from typing import List, Dict, Any



        # 检查文件是否存在
        if not os.path.exists(文件路径):
            错误信息 = f"配置文件不存在: {文件路径}"

            raise FileNotFoundError(错误信息)



        try:
            # 使用 importlib 动态导入，不修改 sys.path
            模块名 = "动态配置模块_" + str(hash(文件路径))
            spec = importlib.util.spec_from_file_location(模块名, 文件路径)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法创建模块规范: {文件路径}")

            配置模块 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(配置模块)

            # 检查是否存在目标配置对象
            if not hasattr(配置模块, "一级子仓库配置"):
                错误信息 = "配置文件中未找到'一级子仓库配置'对象"

                raise ValueError(错误信息)

            配置对象 = getattr(配置模块, "一级子仓库配置")

            # 检查配置对象类型
            if not isinstance(配置对象, list):
                错误信息 = "配置格式错误，'一级子仓库配置'必须为列表"

                raise TypeError(错误信息)

            # 成功
            配置数量 = len(配置对象)
            成功信息 = f"✅ 成功读取配置文件，共 {配置数量} 个一级子仓库"


            return 配置对象

        except SyntaxError:
            错误信息 = "配置文件存在语法错误，请检查"

            raise SyntaxError(错误信息)
        except Exception as e:
            错误信息 = f"导入配置文件时发生错误: {str(e)}"

            raise type(e)(错误信息) from e

# ====================== 【使用示例】 ======================
def main():
    """使用示例"""
    print("Git仓库迁移引擎")
    print("=" * 60)

    # 配置参数
    GITEE_TOKEN = "1bb379b3f7a00eb0547b2e2e98f914b4"  # 请替换为实际的Gitee Token
    顶级仓库URL = ""
    缓存目录 = "./migration_cache"

    # 初始化组件
    api = GiteeApi(GITEE_TOKEN)
    git工具实例 = Git工具()

    # 创建迁移引擎
    引擎 = 迁移引擎(api, git工具实例, 缓存目录)

    # 开始迁移
    引擎.迁移仓库(顶级仓库URL)


if __name__ == "__main__":
    main()
