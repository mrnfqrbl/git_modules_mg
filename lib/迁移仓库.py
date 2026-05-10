from dataclasses import dataclass
# TODO: 处理依赖 包括 requirements.txt setup.py  pyproject.toml
# TODO: 目前预期处理为任务类直接处理任务省略额外递归调用 任务类自包含处理逻辑和向下调用任务类
# TODO: 采用新分支构造来实现基于原提交变更后推送到指定命名的分支然后由外部仓库更新引用实现迁移
# TODO: 新问题： comfyui插件到底要不要保持哈希不变如果保持不变意味着我还要用旧过去的缓存如果不用就无法保证插件还是原来的样子一般情况插件不会更新或者说不会大改
from datetime import datetime, timedelta

#处理状态枚举
from enum import Enum
from typing import Optional

from lib.gdm import 函数通用返回模型
from lib.git_base_api import GiteeApi
from lib.git_command import Git工具


class 处理状态(Enum):
    处理中 = "处理中"
    处理 = "成功"
    处理 = "失败"

    未开始 = "未开始"


# TODO: debug 情况下 错误信息将不再是字符串类型而是log列表
# TODO: 对于这里的log或者说操作记录和状态相关的信息强制返回和做缓存 我可以不看你不可以没有



"""
返回数据：
    仓库名称：仓库名称
    处理状态：处理状态
    子仓库数量：子仓库数量
    依赖数量：依赖数量
    开始时间：开始时间
    结束时间：结束时间
    处理耗时：处理耗时
    子仓库任务列表：子仓库的处理结果字典组成的列表
    处理的依赖列表：处理的依赖的处理结果字典组成的列表

    仓库名称：仓库名称


"""

class 仓库任务:
    def __init__(self, url,gitee_api:GiteeApi,git工具:Git工具,仓库目录:str):
        self.仓库目录=仓库目录
        self.url = url
        self.gitee_api=gitee_api
        self.git工具=git工具

        self.仓库名 = self.url.split("/")[-1].split(".")[0]
        self.处理状态 = 处理状态.未开始
        self.子仓库数量=0
        self.依赖数量=0

        self.开始时间:Optional[datetime]=None
        self.结束时间:Optional[datetime]=None
        self.处理耗时:Optional[timedelta]=None
        self.子仓库任务列表=[]
        self.处理的依赖列表=[]


    def 开始处理(self):
        self.处理状态 = 处理状态.处理中
        self.开始时间=datetime.now()

    def 处理失败(self):
        self.处理状态 = 处理状态.处理失败
        self.结束时间=datetime.now()
        self.处理耗时=self.结束时间-self.开始时间
    def 处理成功(self):
        self.处理状态 = 处理状态.处理成功
        self.结束时间=datetime.now()
        self.处理耗时=self.结束时间-self.开始时间

    def 获取处理结果(self):

        return 函数通用返回模型(状态=函数通用返回模型.成功,数据={
            "仓库名称":self.仓库名,
            "开始时间":self.开始时间.strftime("%Y-%m-%d %H:%M:%S"),
            "结束时间":self.结束时间.strftime("%Y-%m-%d %H:%M:%S"),
            "处理耗时":self.处理耗时.total_seconds(),
            "初始耗时单位":"秒"

        })




    # def 读取子仓库信息(self,仓库目录:str):

