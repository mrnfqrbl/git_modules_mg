import traceback
from typing import Optional, Dict, Any, Generic, TypeVar

from obj2dict import 可序列化基类
from 通用数据模型 import 函数通用返回模型
T = TypeVar('T')
class 函数通用返回模型(函数通用返回模型,Generic[T]):
    """函数通用返回模型"""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.日志: list[str] | None = []
        self.错误堆栈: str | None = None


    def __str__(self):
        return str(self.转字典())
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
        self.状态 = super().成功
        self.数据: T | None = 数据

        return True

    def 失败(self,错误信息: str,异常对象: Exception | None = None,数据: Optional[T] = None):
        """失败返回"""
        self.状态 = super().失败
        self.错误信息: str | None = 错误信息
        self.错误堆栈: str | None = ''.join(traceback.format_exception(type(异常对象), 异常对象, 异常对象.__traceback__)) if 异常对象 else None


        return True





