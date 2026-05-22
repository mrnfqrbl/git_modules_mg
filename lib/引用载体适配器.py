"""
引用载体适配器模块
==================
中间层：负责从仓库工作区中识别、解析、改写各种引用载体文件。
顶层不认识任何文件格式，只通过适配器获取抽象的"依赖边"。

目前实现：
    - GitModules适配器：解析/改写 .gitmodules
    - Requirements适配器：解析/改写 requirements*.txt 中的 git+https:// 依赖
    - SetupPy适配器：解析/改写 setup.py 中的 git 依赖
    - PyProject适配器：解析/改写 pyproject.toml 中的 git 依赖（骨架）

扩展方式：
    新增一个继承 引用载体适配器基类 的子类，注册到 已注册适配器 列表即可。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional
from configparser import ConfigParser


# ─────────────────────────────────────────────
# 依赖边 数据结构（与文件格式无关）
# ─────────────────────────────────────────────
@dataclass
class 依赖边:
    """一条从当前仓库指向外部仓库的引用"""
    url: str                          # 当前指向的完整 URL
    仓库名: str                       # 从 URL 推断的仓库名（不含 .git）
    引用类型: str = "子模块"           # 子模块 | pip依赖 | 可编辑安装
    固定度: str = "浮动到分支"         # 锁定到commit | 浮动到分支 | 浮动到tag
    载体文件: str = ""                # 来源文件路径（审计用）
    载体位置: str = ""                # 文件内定位信息（section名/行号）
    额外信息: dict = field(default_factory=dict)  # 分支名、路径等


# ─────────────────────────────────────────────
# 适配器基类（协议）
# ─────────────────────────────────────────────
class 引用载体适配器基类:
    """
    引用载体适配器协议。
    每种文件格式实现一个子类，对外统一暴露三个方法：
        识别(工作区) → bool
        解析(工作区) → list[依赖边]
        改写(工作区, 映射表) → list[str]  改动记录
    """

    def 识别(self, 工作区路径: str) -> bool:
        """检查工作区中是否存在本适配器负责的文件"""
        raise NotImplementedError

    def 解析(self, 工作区路径: str) -> list[依赖边]:
        """解析文件，返回所有外部引用（依赖边列表）"""
        raise NotImplementedError

    def 改写(self, 工作区路径: str, 映射表: dict[str, str]) -> list[str]:
        """
        根据映射表 {旧URL → 新URL} 改写文件中的引用。
        返回改动记录列表（供审计）。
        """
        raise NotImplementedError


# ─────────────────────────────────────────────
# .gitmodules 适配器
# ─────────────────────────────────────────────
class GitModules适配器(引用载体适配器基类):
    """解析/改写 .gitmodules 文件"""

    def _文件路径(self, 工作区路径: str) -> str:
        return os.path.join(工作区路径, ".gitmodules")

    def 识别(self, 工作区路径: str) -> bool:
        return os.path.isfile(self._文件路径(工作区路径))

    def 解析(self, 工作区路径: str) -> list[依赖边]:
        路径 = self._文件路径(工作区路径)
        if not os.path.isfile(路径):
            return []

        解析器 = ConfigParser()
        解析器.read(路径, encoding="utf-8")

        结果 = []
        for section in 解析器.sections():
            # section 格式：'submodule "xxx"'
            if not section.startswith('submodule "'):
                continue
            名称 = section.split('"')[1]
            url = 解析器.get(section, "url", fallback="")
            path = 解析器.get(section, "path", fallback="")
            branch = 解析器.get(section, "branch", fallback="")

            if not url:
                continue

            仓库名 = url.rstrip("/").split("/")[-1].removesuffix(".git")

            边 = 依赖边(
                url=url,
                仓库名=仓库名,
                引用类型="子模块",
                固定度="浮动到分支",
                载体文件=".gitmodules",
                载体位置=section,
                额外信息={"名称": 名称, "路径": path, "分支": branch,"锁定commit": ""}
            )
            结果.append(边)

        return 结果

    def 改写(self, 工作区路径: str, 映射表: dict[str, str]) -> list[str]:
        """改写 .gitmodules 中的 url 字段（文本替换，保持原始格式）"""
        路径 = self._文件路径(工作区路径)
        if not os.path.isfile(路径):
            return []

        改动记录 = []
        with open(路径, "r", encoding="utf-8") as f:
            内容 = f.read()

        新内容 = 内容
        for 旧url, 新url in 映射表.items():
            if 旧url in 新内容:
                新内容 = 新内容.replace(旧url, 新url)
                改动记录.append(f".gitmodules: {旧url} → {新url}")

        if 新内容 != 内容:
            with open(路径, "w", encoding="utf-8") as f:
                f.write(新内容)

        return 改动记录


# ─────────────────────────────────────────────
# requirements*.txt 适配器
# ─────────────────────────────────────────────
class Requirements适配器(引用载体适配器基类):
    """解析/改写 requirements*.txt 中的 git+https:// 依赖"""

    _PURE_URL_RE = re.compile(
        r'git\+(https?://[^\s@#]+(?:\.git)?)'
    )

    def _查找requirements文件(self, 工作区路径: str) -> list[str]:
        """找到所有 requirements*.txt 文件"""
        结果 = []
        for 文件名 in os.listdir(工作区路径):
            if 文件名.startswith("requirements") and 文件名.endswith(".txt"):
                结果.append(os.path.join(工作区路径, 文件名))
        return 结果

    def 识别(self, 工作区路径: str) -> bool:
        # 路径不存在时（dry-run 未克隆）直接返回 False，不抛 FileNotFoundError
        if not os.path.isdir(工作区路径):
            return False
        return len(self._查找requirements文件(工作区路径)) > 0

    def 解析(self, 工作区路径: str) -> list[依赖边]:
        结果 = []
        for 文件路径 in self._查找requirements文件(工作区路径):
            文件名 = os.path.basename(文件路径)
            with open(文件路径, "r", encoding="utf-8") as f:
                for 行号, 行 in enumerate(f, 1):
                    行 = 行.strip()
                    if not 行 or 行.startswith("#"):
                        continue

                    匹配 = self._PURE_URL_RE.search(行)
                    if not 匹配:
                        continue

                    纯url = 匹配.group(1)
                    仓库名 = 纯url.rstrip("/").split("/")[-1].removesuffix(".git")

                    固定度 = "浮动到分支"
                    分支信息 = ""
                    if "@" in 行.split("://", 1)[-1]:
                        分支信息 = 行.split("@")[-1].split("#")[0].strip()
                        if len(分支信息) == 40:  # SHA1 hash
                            固定度 = "锁定到commit"

                    边 = 依赖边(
                        url=纯url,
                        仓库名=仓库名,
                        引用类型="pip依赖",
                        固定度=固定度,
                        载体文件=文件名,
                        载体位置=f"第{行号}行",
                        额外信息={"原始行": 行, "分支": 分支信息}
                    )
                    结果.append(边)

        return 结果

    def 改写(self, 工作区路径: str, 映射表: dict[str, str]) -> list[str]:
        """改写 requirements*.txt 中的 git URL"""
        改动记录 = []
        for 文件路径 in self._查找requirements文件(工作区路径):
            文件名 = os.path.basename(文件路径)
            with open(文件路径, "r", encoding="utf-8") as f:
                内容 = f.read()

            新内容 = 内容
            for 旧url, 新url in 映射表.items():
                if 旧url in 新内容:
                    新内容 = 新内容.replace(旧url, 新url)
                    改动记录.append(f"{文件名}: {旧url} → {新url}")

            if 新内容 != 内容:
                with open(文件路径, "w", encoding="utf-8") as f:
                    f.write(新内容)

        return 改动记录


# ─────────────────────────────────────────────
# setup.py 适配器
# ─────────────────────────────────────────────
class SetupPy适配器(引用载体适配器基类):
    """解析/改写 setup.py 中的 git 依赖"""

    _PURE_URL_RE = re.compile(
        r'git\+(https?://[^\s\'"@#,]+(?:\.git)?)'
    )

    def _文件路径(self, 工作区路径: str) -> str:
        return os.path.join(工作区路径, "setup.py")

    def 识别(self, 工作区路径: str) -> bool:
        路径 = self._文件路径(工作区路径)
        if not os.path.isfile(路径):
            return False
        # 只有包含 git+ 引用才算"有我负责的内容"
        with open(路径, "r", encoding="utf-8") as f:
            return "git+" in f.read()

    def 解析(self, 工作区路径: str) -> list[依赖边]:
        路径 = self._文件路径(工作区路径)
        if not os.path.isfile(路径):
            return []

        结果 = []
        with open(路径, "r", encoding="utf-8") as f:
            内容 = f.read()

        for 匹配 in self._PURE_URL_RE.finditer(内容):
            纯url = 匹配.group(1)
            仓库名 = 纯url.rstrip("/").split("/")[-1].removesuffix(".git")
            边 = 依赖边(
                url=纯url,
                仓库名=仓库名,
                引用类型="pip依赖",
                固定度="浮动到分支",
                载体文件="setup.py",
                载体位置="install_requires/dependency_links",
            )
            结果.append(边)

        return 结果

    def 改写(self, 工作区路径: str, 映射表: dict[str, str]) -> list[str]:
        路径 = self._文件路径(工作区路径)
        if not os.path.isfile(路径):
            return []

        改动记录 = []
        with open(路径, "r", encoding="utf-8") as f:
            内容 = f.read()

        新内容 = 内容
        for 旧url, 新url in 映射表.items():
            if 旧url in 新内容:
                新内容 = 新内容.replace(旧url, 新url)
                改动记录.append(f"setup.py: {旧url} → {新url}")

        if 新内容 != 内容:
            with open(路径, "w", encoding="utf-8") as f:
                f.write(新内容)

        return 改动记录


# ─────────────────────────────────────────────
# pyproject.toml 适配器（骨架，后续按需完善）
# ─────────────────────────────────────────────
class PyProject适配器(引用载体适配器基类):
    """解析/改写 pyproject.toml 中的 git 依赖（骨架）"""
    # TODO: 完整实现 toml 结构化解析（需要 toml/tomllib），当前用正则兜底

    _PURE_URL_RE = re.compile(
        r'git\+(https?://[^\s\'"@#,]+(?:\.git)?)'
    )

    def _文件路径(self, 工作区路径: str) -> str:
        return os.path.join(工作区路径, "pyproject.toml")

    def 识别(self, 工作区路径: str) -> bool:
        路径 = self._文件路径(工作区路径)
        if not os.path.isfile(路径):
            return False
        with open(路径, "r", encoding="utf-8") as f:
            return "git+" in f.read()

    def 解析(self, 工作区路径: str) -> list[依赖边]:
        路径 = self._文件路径(工作区路径)
        if not os.path.isfile(路径):
            return []

        结果 = []
        with open(路径, "r", encoding="utf-8") as f:
            内容 = f.read()

        for 匹配 in self._PURE_URL_RE.finditer(内容):
            纯url = 匹配.group(1)
            仓库名 = 纯url.rstrip("/").split("/")[-1].removesuffix(".git")
            边 = 依赖边(
                url=纯url,
                仓库名=仓库名,
                引用类型="pip依赖",
                固定度="浮动到分支",
                载体文件="pyproject.toml",
                载体位置="dependencies",
            )
            结果.append(边)

        return 结果

    def 改写(self, 工作区路径: str, 映射表: dict[str, str]) -> list[str]:
        路径 = self._文件路径(工作区路径)
        if not os.path.isfile(路径):
            return []

        改动记录 = []
        with open(路径, "r", encoding="utf-8") as f:
            内容 = f.read()

        新内容 = 内容
        for 旧url, 新url in 映射表.items():
            if 旧url in 新内容:
                新内容 = 新内容.replace(旧url, 新url)
                改动记录.append(f"pyproject.toml: {旧url} → {新url}")

        if 新内容 != 内容:
            with open(路径, "w", encoding="utf-8") as f:
                f.write(新内容)

        return 改动记录


# ─────────────────────────────────────────────
# 全局注册表：所有已注册适配器（顶层直接遍历这个列表）
# ─────────────────────────────────────────────
已注册适配器: list[引用载体适配器基类] = [
    GitModules适配器(),
    Requirements适配器(),
    SetupPy适配器(),
    PyProject适配器(),
]


# ─────────────────────────────────────────────
# 便捷函数（供任务类直接调用）
# ─────────────────────────────────────────────
def 收集所有依赖(工作区路径: str) -> list[依赖边]:
    """遍历所有适配器，收集工作区中的全部外部引用"""
    全部依赖 = []
    for 适配器 in 已注册适配器:
        if 适配器.识别(工作区路径):
            全部依赖.extend(适配器.解析(工作区路径))
    return 全部依赖


def 改写所有引用(工作区路径: str, 映射表: dict[str, str]) -> list[str]:
    """遍历所有适配器，按映射表改写工作区中的全部引用"""
    全部改动 = []
    for 适配器 in 已注册适配器:
        if 适配器.识别(工作区路径):
            全部改动.extend(适配器.改写(工作区路径, 映射表))
    return 全部改动


def 检查引用是否已指向目标(url: str, 目标域名列表: list[str]) -> bool:
    """
    检查一个 URL 是否已经指向目标平台。
    用于跳过判断：如果已指向目标域名，说明已迁移过，无需再处理。
    """
    for 域名 in 目标域名列表:
        if 域名 in url:
            return True
    return False
