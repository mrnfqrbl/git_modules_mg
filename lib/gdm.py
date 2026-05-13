import traceback
from enum import Enum
from typing import Optional, Dict, Any, Generic, TypeVar

from obj2dict import 可序列化基类
from 通用数据模型 import 函数通用返回模型
T = TypeVar('T')

class 函数通用返回模型(函数通用返回模型,Generic[T]):
    """函数通用返回模型"""
    def __init__(self,*args,**kwargs):
        self.日志: list[str] | None = []
        self.错误堆栈: str | None = None
        self.状态: bool = False
        self.错误信息: str | None = None
        self.数据: T | None = None
    def __setattr__(self, name, value):
        if name == "状态":
            if not isinstance(value, bool):
                raise ValueError(f"状态只能是bool类型，收到: {value}")
        self.__dict__[name] = value

    def __str__(self):
        # 在这里定义你【强制固定的顺序】
        固定顺序 = ["状态", "错误信息", "错误堆栈", "数据", "日志"]

        字典 = self.转字典()
        有序结果 = {}

        # 1. 先放你指定顺序的字段
        for key in 固定顺序:
            if key in 字典:
                有序结果[key] = 字典[key]

        # 2. 再放剩下的动态字段（按插入顺序）
        for key, value in 字典.items():
            if key not in 有序结果:
                有序结果[key] = value

        return str(有序结果)
    def __repr__(self):
        return str(self.转字典())
    def 添加日志(self,日志: str):
        """添加日志"""
        self.日志.append(日志)
        return True



    def 清空日志(self):
        """清空日志"""
        self.日志.clear()
        return True


    def 成功(self,数据: Optional[T] = None):
        """成功返回"""
        self.状态 = True
        self.数据: T | None = 数据

        return True

    def 失败(self,错误信息: str,异常对象: Exception | None = None,数据: Optional[T] = None):
        """失败返回"""
        self.状态 = False
        self.错误信息: str | None = 错误信息
        self.错误堆栈: str | None = ''.join(traceback.format_exception(type(异常对象), 异常对象, 异常对象.__traceback__)) if 异常对象 else None


        return True





