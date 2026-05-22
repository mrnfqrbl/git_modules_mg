import gc
import os
import shutil
import stat

import subprocess
import sys
import time
import traceback
from typing import List, Dict, Optional, Any

import git
from git import Repo, GitCommandError, InvalidGitRepositoryError,Submodule
from lib.gdm import 函数通用返回模型
from lib.util import 解决win权限问题


class git操作:
    """
    GitPython 可实例化封装 + 静态工具方法
    实例化后维护 repo 对象，提供提交、推送、子模块管理等实例方法
    静态方法提供拉库、删库、查询等无需绑定仓库的操作，内部通过临时实例复用逻辑
    """
    _实例表={}
    def __new__(cls,仓库路径: str, *args, **kwargs,):
        #如果存在仓库路径为当前路径的实例直接返回
        if 仓库路径 in cls._实例表:
            return cls._实例表[仓库路径]

        新实例 = super().__new__(cls,*args, **kwargs)

        # 3. 存入实例表（关键！你之前漏了这步）
        cls._实例表[仓库路径] = 新实例

        # 4. 返回单例实例
        return 新实例


    def __init__(self, 仓库路径: str):
        """
        初始化实例，绑定有效的 Git 仓库
        :param 仓库路径: 本地仓库的绝对或相对路径
        :raises: 若路径无效或非 Git 仓库，抛出异常
        """
        if getattr(self, "_已初始化", False):
            return
        if not os.path.isdir(仓库路径):
            raise ValueError(f"路径不存在或不是目录: {仓库路径}")
        if not os.path.exists(os.path.join(仓库路径, ".git")):
            raise ValueError(f"不是有效的 Git 仓库: {仓库路径}")
        try:
            self.repo = Repo(仓库路径)
            self.仓库路径 = 仓库路径
        except InvalidGitRepositoryError:
            raise ValueError(f"无效的 Git 仓库: {仓库路径}")
        self._已初始化 = True

    # ====================== 【仓库校验 · 查询类】（实例方法） ======================
    # 标记:已测试
    def 获取当前分支(self, test: bool = False) -> 函数通用返回模型:
        """实例方法：查询本地仓库当前分支名称"""
        返回 = 函数通用返回模型()
        if test:
            返回.成功(数据="测试模式")
            return 返回
        try:
            返回.成功(数据=self.repo.active_branch.name)
        except Exception as e:
            返回.失败(f"查询失败：{str(e)}", 异常对象=e)
        return 返回

    def 获取HEAD(self, test: bool = False) -> 函数通用返回模型:
        """获取当前 HEAD 的 commit hash（detached 也能读）"""
        返回 = 函数通用返回模型()
        if test:
            返回.成功(数据="0" * 40)
            return 返回
        try:
            返回.成功(数据=self.repo.head.commit.hexsha)
        except Exception as e:
            返回.失败(f"获取HEAD失败：{str(e)}", 异常对象=e)
        return 返回

    def checkout(self, 引用: str, 强制: bool = False, test: bool = False) -> 函数通用返回模型:
        """切换到指定分支/标签/commit。强制=True 会丢弃未提交修改。"""
        返回 = 函数通用返回模型()
        if test:
            返回.成功(数据=引用)
            return 返回
        try:
            参数 = ["checkout"]
            if 强制:
                参数.append("--force")
            参数.append(引用)
            self.repo.git.execute(["git"] + 参数)
            返回.成功(数据=引用)
        except Exception as e:
            返回.失败(f"checkout 失败：{str(e)}", 异常对象=e)
        return 返回

    # 标记:已测试

    def 是否有未提交更改(self, test: bool = False) -> 函数通用返回模型:
        """实例方法：校验仓库是否有未提交的修改（新增/修改/删除文件）"""
        返回 = 函数通用返回模型()
        if test:
            # 测试模式：仅模拟检查，返回一个模拟结果（假设有未提交更改？或根据实际？这里简单返回False表示测试通过）
            返回.成功(数据=False)
            return 返回
        try:
            返回.成功(数据=self.repo.is_dirty(untracked_files=True))
        except Exception as e:
            返回.失败(f"查询失败：{str(e)}", 异常对象=e)
        return 返回
    # 标记:已测试
    def 获取远程地址(self, 远程名称: str = "origin", test: bool = False) -> 函数通用返回模型:
        """实例方法：查询本地仓库关联的远程仓库地址"""
        返回 = 函数通用返回模型()
        if test:
            返回.成功(数据="测试模式://模拟地址")
            return 返回
        try:
            返回.成功(数据=self.repo.remotes[远程名称].url)
        except (GitCommandError, IndexError) as e:
            返回.失败(f"未关联远程仓库 '{远程名称}'", 异常对象=e)
        except Exception as e:
            返回.失败(f"查询失败：{str(e)}", 异常对象=e)
        return 返回
    # 标记:已测试
    def 获取子模块列表(self, test: bool = False) -> 函数通用返回模型[List[Dict[str, Any]]]:
        """实例方法：查询本地仓库的子模块列表"""
        返回 = 函数通用返回模型()
        if test:
            返回.成功(数据=[])
            return 返回
        try:
            data = []
            for submodule in self.repo.submodules:
                # 读 .gitmodules 中的 branch 字段，避免 submodule.branch 在未配置时报错
                追踪分支 = ""
                try:
                    with submodule.config_reader() as cr:
                        if cr.has_option("branch"):
                            追踪分支 = cr.get("branch") or ""
                except Exception:
                    追踪分支 = ""
                data.append({
                    "名称": submodule.name,
                    "路径": submodule.path,
                    "追踪分支": 追踪分支,
                    "锁定的提交哈希": submodule.hexsha,
                    "URL": submodule.url,
                })
            返回.成功(数据=data)
        except GitCommandError as e:
            返回.失败(f"git命令执行错误：{str(e)}", 异常对象=e)
        except Exception as e:
            返回.失败(f"查询失败：{str(e)}", 异常对象=e)
        return 返回
    # 标记:已测试
    def 获取子模块信息(self, 子模块名称: str, test: bool = False) -> 函数通用返回模型[Dict[str, Any]]:
        """实例方法：获取单个子模块的详细信息"""
        返回 = 函数通用返回模型()
        if test:
            返回.成功(数据={"名称": 子模块名称, "测试模式": True})
            return 返回
        try:
            submodule = self.repo.submodule(子模块名称)
            追踪分支 = ""
            try:
                with submodule.config_reader() as cr:
                    if cr.has_option("branch"):
                        追踪分支 = cr.get("branch") or ""
            except Exception:
                追踪分支 = ""
            data = {
                "名称": submodule.name,
                "路径": submodule.path,
                "追踪分支": 追踪分支,
                "锁定的提交哈希": submodule.hexsha,
                "URL": submodule.url,
            }
            返回.成功(数据=data)
        except (IndexError, ValueError) as e:
            返回.失败(f"子模块 '{子模块名称}' 不存在", 异常对象=e)
        except Exception as e:
            返回.失败(f"查询失败：{str(e)}", 异常对象=e)
        return 返回

    # ====================== 【本地管理 · 基础操作】（实例方法） ======================
    # 标记:已测试
    def 添加(self, 文件列表: Optional[List[str]] = None, test: bool = False) -> 函数通用返回模型:
        """
        实例方法：将文件添加到暂存区
        :param 文件列表: 要添加的文件列表，None 表示添加所有变更（git add -A）
        :param test: 测试模式（dry-run）
        """
        返回 = 函数通用返回模型()
        try:
            if test:
                # 使用 git add --dry-run
                if 文件列表 is None:
                    data=self.repo.git.add(A=True, dry_run=True)
                else:
                    data=self.repo.git.add(文件列表, dry_run=True)
                返回.成功(数据=data)
                return 返回

            if 文件列表 is None:
                data=self.repo.git.add(A=True)   # git add -A
            else:
                data=self.repo.git.add(文件列表)
            返回.成功(数据=data)
        except Exception as e:
            返回.失败(f"添加失败：{str(e)}", 异常对象=e)
        return 返回
    # 标记:已测试
    def 提交(self, 提交信息: str, 文件列表: Optional[List[str]] = None,
             是否允许自动add: bool = False, test: bool = False) -> 函数通用返回模型:
        """
        实例方法：提交更改
        :param 提交信息: commit message
        :param 文件列表: 要提交的文件列表，None 表示根据 是否允许自动add 决定行为
        :param 是否允许自动add: 若为 True 且文件列表为 None，则自动暂存所有变更（git add -A）
        :param test: 测试模式（dry-run）
        """
        返回 = 函数通用返回模型()
        try:
            # 处理文件暂存
            if 文件列表 is not None:
                # 用户明确指定了文件列表，直接添加这些文件（不自动添加所有）
                add_ret = self.添加(文件列表, test=test)
                if not add_ret.状态:
                    return add_ret
            else:
                # 文件列表为 None
                if 是否允许自动add:
                    # 自动添加所有变更
                    add_ret = self.添加(None, test=test)
                    if not add_ret.状态:
                        return add_ret

                # 否则不添加任何新文件，只提交已暂存的内容（无需额外操作）

            if test:
                # 使用 git commit --dry-run
                if 文件列表 is not None or 是否允许自动add:
                    # 已经执行过 add --dry-run，再执行 commit --dry-run
                    self.repo.git.commit(m=提交信息, dry_run=True)
                else:
                    # 只提交已暂存的内容，也需要 dry-run
                    self.repo.git.commit(m=提交信息, dry_run=True)
                返回.成功(数据="测试提交哈希模拟")
                return 返回

            # 实际提交
            commit = self.repo.index.commit(提交信息)
            返回.成功(数据=commit.hexsha)

        except Exception as e:
            返回.失败(f"提交失败：{str(e)}", 异常对象=e)
        return 返回
    # 标记:已测试
    def 推送(self, 远程名称: str = "origin", 分支: Optional[str] = None, test: bool = False,强制:bool=False) -> 函数通用返回模型:
        """
        实例方法：推送到远程仓库
        :param 远程名称: 远程仓库名称，默认 origin
        :param 分支: 要推送的分支，None 表示当前分支
        :param test: 测试模式（dry-run）
        """
        返回 = 函数通用返回模型()
        try:
            if 分支 is None:
                分支 = self.repo.active_branch.name
            if test:
                # 使用 git push --dry-run
                remote = self.repo.remotes[远程名称]
                remote.push(refspec=分支, dry_run=True,force=强制)
                返回.成功(数据=True)
                return 返回

            remote = self.repo.remotes[远程名称]
            push_info = remote.push(refspec=分支,force=强制)
            for info in push_info:
                if info.flags & info.ERROR:
                    返回.失败(f"推送失败：{info.summary}")
                    return 返回
            返回.成功(数据=True)
            # # 简单判断是否成功
            # if push_info and hasattr(push_info[0], 'flags'):
            #     # flags 非零通常表示成功，具体可参考 git.PushInfo
            #     返回.成功(数据=True)
            # else:
            #     for info in push_info:
            #         if info.flags & info.ERROR:
            #             返回.失败(f"推送失败：{info.summary}")
            #             return 返回
            # 返回.成功(数据=True)
        except Exception as e:
            返回.失败(f"推送失败：{str(e)}", 异常对象=e)
        return 返回

    # ====================== 【子模块管理】（实例方法） ======================
    # 标记:已测试
    def 添加子模块(self, 名称: str, 路径: str, 远程地址: str, 分支: Optional[str] = None,
                   test: bool = False) -> 函数通用返回模型:
        """
        实例方法：添加子模块
        :param 名称: 子模块名称
        :param 路径: 子模块本地存放路径（相对于仓库根目录）
        :param 远程地址: 子模块的远程仓库 URL
        :param 分支: 要追踪的分支，None 则使用默认分支
        :param test: 测试模式（dry-run）
        """
        返回 = 函数通用返回模型()
        if test:
            # 模拟添加，不实际执行
            self.repo.git.submodule("add", "--dry-run", "--name", 名称, 远程地址, 路径)
            返回.成功(数据={"名称": 名称, "路径": 路径, "测试模式": True})
            return 返回

        # 1. 规范化并清洗追踪分支名称
        原追踪分支 = 分支.strip() if (分支 and isinstance(分支, str)) else None
        if not 原追踪分支:
            原追踪分支 = None

        try:
            # 2. 强制使用 branch=None 进行全量无分支克隆，确保 100% 能够拉取成功
            submodule = self.repo.create_submodule(名称, 路径, url=远程地址, branch=None)

            # 3. 克隆成功后，如果原先有追踪分支，将追踪分支配置写回以保留元数据
            if 原追踪分支:
                try:
                    with submodule.config_writer() as cw:
                        cw.set_value("branch", 原追踪分支)
                except Exception:
                    pass

            返回.成功(数据={
                "名称": submodule.name,
                "路径": submodule.path,
                "锁定的提交哈希": submodule.hexsha
            })
        except Exception as e:
            # 4. 原子回滚清扫：若拉取由于网络等原因彻底失败，自动清扫半吊子残留以防下次冲突
            try:
                self.删除子模块(名称)
            except Exception:
                pass
            返回.失败(f"添加子模块失败：{str(e)}", 异常对象=e)
        return 返回
    # 标记:已测试
    def 删除子模块(self, 名称: str, 强制: bool = False, test: bool = False) -> 函数通用返回模型:
        """
        实例方法：删除子模块
        :param 名称: 子模块名称
        :param 强制: 是否强制删除（忽略未提交变更）
        :param test: 测试模式（dry-run）
        """
        返回 = 函数通用返回模型()
        if test:
            # 仅检查子模块是否存在
            try:
                self.repo.submodule(名称)
                返回.成功(数据=True)
            except Exception:
                返回.失败(f"子模块 '{名称}' 不存在", 异常对象=None)
            return 返回
        try:
            try:
                submodule = self.repo.submodule(名称)
                模块路径 = submodule.path
                模块名称 = submodule.name
            except Exception:
                submodule = None
                模块路径 = None
                模块名称 = 名称
                # 尝试从 .gitmodules 中读取路径
                try:
                    gitmodules路径 = os.path.join(self.仓库路径, ".gitmodules")
                    if os.path.isfile(gitmodules路径):
                        from git.config import GitConfigParser
                        with GitConfigParser(gitmodules路径, read_only=True) as gcp:
                            section = f'submodule "{名称}"'
                            if gcp.has_section(section) and gcp.has_option(section, "path"):
                                模块路径 = gcp.get(section, "path")
                except Exception:
                    pass
                if not 模块路径:
                    模块路径 = 名称

            模块完整路径 = os.path.join(self.仓库路径, 模块路径)
            索引路径 = os.path.join(self.仓库路径, ".git", "modules", 模块名称)

            # 只有在子仓库实际存在且已初始化时才尝试清理其缓存并关闭
            if submodule and submodule.module_exists():
                try:
                    subrepo = submodule.module()
                    subrepo.git.clear_cache()
                    subrepo.close()
                    del subrepo
                except Exception:
                    pass

            if submodule:
                del submodule
            gc.collect()

            # deinit 子模块
            try:
                self.repo.git.submodule("deinit", "--force", 模块路径)
            except Exception:
                pass

            # 从 git index 中移除
            try:
                self.repo.git.rm("--cached", "--force", 模块路径)
            except Exception:
                pass

            # 删除 .git/modules 中的缓存索引路径
            if os.path.exists(索引路径):
                try:
                    shutil.rmtree(索引路径, onerror=解决win权限问题)
                except Exception:
                    pass
            del 索引路径

            # 删除子仓库工作区目录路径
            if os.path.exists(模块完整路径):
                try:
                    if os.path.isdir(模块完整路径) and not os.path.islink(模块完整路径):
                        shutil.rmtree(模块完整路径, onerror=解决win权限问题)
                    else:
                        os.remove(模块完整路径)
                except Exception:
                    pass
            del 模块完整路径

            # 从仓库的 config 中删除配置项
            try:
                with self.repo.config_writer(config_level="repository") as cw:
                    section = f'submodule "{模块名称}"'
                    if cw.has_section(section):
                        cw.remove_section(section)
            except Exception:
                pass

            # 从 .gitmodules 文件中删除配置项
            try:
                gitmodules路径 = os.path.join(self.仓库路径, ".gitmodules")
                if os.path.isfile(gitmodules路径):
                    from git.config import GitConfigParser
                    with GitConfigParser(gitmodules路径, read_only=False) as gcp:
                        section = f'submodule "{模块名称}"'
                        if gcp.has_section(section):
                            gcp.remove_section(section)
            except Exception:
                pass

            返回.成功(数据=True)
        except Exception as e:
            返回.失败(f"删除子模块失败：{str(e)}", 异常对象=e)
        return 返回



    def 更新子模块(self, 名称: Optional[str] = None, 递归: bool = False, 初始化: bool = False, test: bool = False
) -> 函数通用返回模型:
        """
        实例方法：更新子模块（拉取远程最新提交）
        :param 名称: 子模块名称，None 表示更新所有子模块
        :param 递归: 是否递归更新子模块内的子模块
        :param test: 测试模式（dry-run）
        """
        返回 = 函数通用返回模型()
        if test:
            if 名称:
                # 检查子模块存在性
                try:
                    self.repo.submodule(名称)
                except Exception:
                    返回.失败(f"子模块 '{名称}' 不存在", 异常对象=None)
                    return 返回
            # 使用 git submodule update --dry-run
            cmd = ["submodule", "update", "--dry-run"]
            if 递归:
                cmd.append("--recursive")
            if 名称:
                cmd.append(名称)
            self.repo.git.cmd.execute(cmd)
            返回.成功(数据=True)
            return 返回
        try:
            if 名称:
                submodule = self.repo.submodule(名称)
                submodule.update(recursive=递归, init=初始化)
            else:
                self.repo.git.submodule("update", "--init", "--recursive" if 递归 else "")
            返回.成功(数据=True)
        except Exception as e:
            返回.失败(f"更新子模块失败：{str(e)}", 异常对象=e)
        return 返回

    # ====================== 【静态方法 · 仓库生命周期与工具】 ======================
    # 所有静态方法内部通过创建临时实例复用实例逻辑，避免重复代码
    # 静态方法同样支持 test 参数，并传递给临时实例

    @staticmethod
    # 标记 ：已测试
    def 是否为有效仓库(仓库路径: str, test: bool = False) -> 函数通用返回模型:
        """校验指定路径是否是合法的Git本地仓库"""
        返回 = 函数通用返回模型()
        if test:
            # 测试模式：简单检查路径是否存在即可
            if os.path.isdir(仓库路径):
                返回.成功(数据=True)
            else:
                返回.成功(数据=False)
            return 返回
        if not os.path.isdir(仓库路径):
            返回.成功(数据=False)
            return 返回
        if not os.path.exists(os.path.join(仓库路径, ".git")):
            返回.成功(数据=False)
            return 返回
        try:
            Repo(仓库路径)
            返回.成功(数据=True)
            return 返回
        except InvalidGitRepositoryError:
            返回.成功(数据=False)
            return 返回
        except Exception as e:
            返回.失败(f"校验失败：{str(e)}", 异常对象=e)
            return 返回

    @staticmethod
    # 标记 ：已测试
    def 目标仓库是否有未提交更改(仓库路径: str, test: bool = False) -> 函数通用返回模型:
        """校验仓库是否有未提交的修改（新增/修改/删除文件）"""
        try:
            op = git操作(仓库路径)
            return op.是否有未提交更改(test=test)
        except Exception as e:
            返回 = 函数通用返回模型()
            返回.失败(f"创建仓库实例失败：{str(e)}", 异常对象=e)
            return 返回

    @staticmethod
    # 标记 ：已测试
    def 获取目标仓库远程地址(仓库路径: str, 远程名称: str = "origin", test: bool = False) -> 函数通用返回模型:
        """查询本地仓库关联的远程仓库地址"""
        try:
            op = git操作(仓库路径)
            return op.获取远程地址(远程名称, test=test)
        except Exception as e:
            返回 = 函数通用返回模型()
            返回.失败(f"创建仓库实例失败：{str(e)}", 异常对象=e)
            return 返回

    @staticmethod
    # 标记 ：已测试
    def 获取目标仓库子模块列表(仓库路径: str, test: bool = False) -> 函数通用返回模型[List[Dict[str, Any]]]:
        """查询本地仓库的子模块列表"""
        try:
            op = git操作(仓库路径)
            return op.获取子模块列表(test=test)
        except Exception as e:
            返回 = 函数通用返回模型()
            返回.失败(f"创建仓库实例失败：{str(e)}", 异常对象=e)
            return 返回

    @staticmethod
    # 标记:已测试
    def 获取目标仓库子模块信息(仓库路径: str, 子模块名称: str, test: bool = False) -> 函数通用返回模型[Dict[str, Any]]:
        """静态方法：获取单个子模块信息"""
        try:
            op = git操作(仓库路径)
            return op.获取子模块信息(子模块名称, test=test)
        except Exception as e:
            返回 = 函数通用返回模型()
            返回.失败(f"创建仓库实例失败：{str(e)}", 异常对象=e)
            return 返回

    @staticmethod
    # 标记 ：已测试
    def clone(远程仓库地址: str, 目标路径: str, test: bool = False) -> 函数通用返回模型:
        """克隆远程仓库到本地"""
        返回 = 函数通用返回模型()
        if test:
            # 测试模式：仅检查目标路径是否存在，不实际克隆
            if os.path.exists(目标路径):
                返回.失败(f"目标路径已存在：{目标路径}", 数据=False)
            else:
                返回.成功(数据=True)
            return 返回

        最大尝试次数 = 3
        等待时间 = 2

        for 尝试 in range(1, 最大尝试次数 + 1):
            try:
                # 在重试开始前，如果有残留目录，强力清理
                if 尝试 > 1 and os.path.exists(目标路径):
                    try:
                        shutil.rmtree(目标路径, onerror=解决win权限问题)
                    except Exception as clean_err:
                        sys.stderr.write(f"清理残留路径失败: {目标路径}, 错误: {clean_err}\n")

                Repo.clone_from(url=远程仓库地址, to_path=目标路径)
                返回.成功(数据=True)
                return 返回
            except Exception as e:
                if 尝试 < 最大尝试次数:
                    sys.stderr.write(f"警告：[git clone] 克隆 {远程仓库地址} 失败 (第 {尝试} 次尝试): {str(e)}，将在 {等待时间} 秒后重试...\n")
                    sys.stderr.flush()
                    time.sleep(等待时间)
                    等待时间 *= 2
                else:
                    返回.失败(f"克隆失败：{str(e)}", 异常对象=e, 数据=False)
        return 返回

    @staticmethod
    # 标记 ：已测试
    def remove(仓库路径: str, test: bool = False) -> 函数通用返回模型:
        """删除本地仓库"""
        返回 = 函数通用返回模型()
        if not Git工具.是否为有效仓库(仓库路径).数据:
            返回.失败(f"路径不是有效 Git 仓库：{仓库路径}", 数据=False)
            return 返回
        if test:
            返回.成功(数据=True)
            return 返回
        repo=Git工具(仓库路径)

        repo.repo.git.clear_cache()
        repo.repo.close()
        Git工具._实例表.pop(仓库路径,None)
        #强制gc
        gc.collect()

        try:

            shutil.rmtree(仓库路径, onerror=解决win权限问题)
            返回.成功(数据=True)
        except Exception as e:
            返回.失败(f"删除失败：{str(e)}")
        return 返回

Git工具=git操作

if __name__ == "__main__":
    #做出一个严重异常的错误操作
    # try:
    #     raise Exception("这是一个严重异常")
    # except Exception as e:
    #      a={"错误信息":str(e),"错误堆栈":''.join(traceback.format_exception(type(e), e, e.__traceback__))}
    #      sys.stderr.write(a["错误堆栈"])
    #
    # raise Exception("这是一个严重异常")


    url="https://github.com/mrnfqrbl/test1.git"
    url2="https://gitee.com/mrnf/test1.git"

    path=r"D:\temp\test1_tt"
    print(git操作.clone(url, path))

    #
    repo=Git工具(r"D:\temp\test1_tt")
    print(repo.更新子模块(递归=True,初始化=True))

    print(repo.获取子模块列表())
    # print(repo.删除子模块("t1",True))
    # print(repo.获取子模块列表())
    # print(repo.添加子模块("t1","com/t1", "https://github.com/mrnfqrbl/sd-forge-colab.git"))
    # print(repo.添加子模块("t3","t1", "https://github.com/mrnfqrbl/sd-forge-colab.git"))
    # print(repo.获取子模块列表())
    #
    #
    # print(repo.提交("添加子模块 t1",是否允许自动add=True))
    # print(repo.推送("origin", repo.获取当前分支().数据))
    #
    #







