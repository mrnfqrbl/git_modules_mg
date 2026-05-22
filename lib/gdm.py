import os
import sys
import traceback
from typing import Optional, Generic, TypeVar

# ── GenDataMod 可选依赖（优先使用，不存在时降级为自包含实现）─────────────────
# GenDataMod 以 git 子模块形式存放在 lib/GenDataMod/
# 安装方式：pip install -e lib/GenDataMod
# 或直接加入 sys.path（下方自动处理）
_gdm_src = os.path.join(os.path.dirname(__file__), "GenDataMod", "src")
if os.path.isdir(_gdm_src) and _gdm_src not in sys.path:
    sys.path.insert(0, _gdm_src)

try:
    from obj2dict import 可序列化基类      # noqa: F401
    from 通用数据模型 import 函数通用返回模型 as _外部基类
    _有外部基类 = True
except ImportError:
    # GenDataMod 尚未安装/拉取，使用完全自包含实现
    _有外部基类 = False

T = TypeVar("T")


# ── 自包含核心实现（两种模式共用逻辑，避免重复）────────────────────────────
class _函数通用返回模型核心(Generic[T]):
    """函数通用返回模型 —— 自包含核心实现"""

    def __init__(self):
        self.日志: list[str] = []
        self.错误堆栈: str | None = None
        self.状态: bool = False
        self.错误信息: str | None = None
        self.数据: T | None = None

    def __setattr__(self, name, value):
        if name == "状态" and not isinstance(value, bool):
            raise ValueError(f"状态只能是bool类型，收到: {value}")
        self.__dict__[name] = value

    def 转字典(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    def __str__(self):
        固定顺序 = ["状态", "错误信息", "错误堆栈", "数据", "日志"]
        字典 = self.转字典()
        有序结果 = {}
        for key in 固定顺序:
            if key in 字典:
                有序结果[key] = 字典[key]
        for key, value in 字典.items():
            if key not in 有序结果:
                有序结果[key] = value
        return str(有序结果)

    def __repr__(self):
        return str(self.转字典())

    def 添加日志(self, 日志: str):
        """添加日志"""
        self.日志.append(日志)
        return True

    def 清空日志(self):
        """清空日志"""
        self.日志.clear()
        return True

    def 成功(self, 数据: Optional[T] = None):
        """成功返回"""
        self.状态 = True
        self.数据 = 数据
        return True

    def 失败(self, 错误信息: str, 异常对象: Exception | None = None, 数据: Optional[T] = None):
        """失败返回"""
        self.状态 = False
        self.错误信息 = 错误信息
        self.数据 = 数据
        self.错误堆栈 = (
            "".join(traceback.format_exception(type(异常对象), 异常对象, 异常对象.__traceback__))
            if 异常对象 else None
        )
        return True


# ── 对外导出类（根据是否有外部依赖选择继承链）────────────────────────────────
if _有外部基类:
    class 函数通用返回模型(_外部基类, _函数通用返回模型核心[T]):   # type: ignore[misc]
        """函数通用返回模型（继承 GenDataMod 外部基类版）"""
        def __init__(self):
            _函数通用返回模型核心.__init__(self)
else:
    class 函数通用返回模型(_函数通用返回模型核心[T]):              # type: ignore[misc]
        """函数通用返回模型（自包含降级版，GenDataMod 未安装时启用）"""
        pass





