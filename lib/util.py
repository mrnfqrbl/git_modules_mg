#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================
【强制规范 · 不可修改】
所有工具函数返回值 统一固定结构：
tuple[执行结果(Any), 简要信息(str), 详细日志列表(list)]
    1. 执行结果：函数核心返回值（如Token值/校验布尔值）
    2. 简要信息：单行文本提示（成功/失败原因）
    3. 详细日志：结构化全流程日志，debug=True采集，debug=False为空列表
=============================================
功能说明：
1. 通用环境变量读取工具（自动遍历+校验）
2. GitHub/Gitee Token极速校验工具（无依赖）
3. 内置全自动结构化日志采集器
"""
import os
import socket
import stat
import time
from typing import Callable, Optional, Any
from urllib import request, error
from lib.func_in_tc import 探测函数参数,取安全关键字参数

# ====================== 【核心】通用结构化日志采集器（自动记录，仅采集不输出） ======================


def 解决win权限问题(删除函数, 目标路径, 异常信息):
    # 仅处理权限拒绝的情况
    if isinstance(异常信息[1], PermissionError):
        # 取消Windows文件/目录的只读属性，赋予所有者写权限
        os.chmod(目标路径, stat.S_IRUSR | stat.S_IWUSR)
        # 重试删除操作
        删除函数(目标路径)
    else:
        # 非权限错误（如文件被进程占用）抛出原异常
        raise


class ToolLogger:
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.log_list = []  # 日志存储列表（静默采集，不主动打印）

    def add(self, module: str, step: str, action: str, params: dict = None, result: Any = None):
        """标准化添加日志：模块+步骤+动作+输入参数+输出结果"""
        if not self.debug:
            return
        log_item = {
            "模块": module,
            "步骤": step,
            "动作": action,
            "输入参数": params or {},
            "结果": str(result) if result is not None else "执行中",
            "时间": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        }
        self.log_list.append(log_item)

    def 合并日志(self, 日志列表: list):
        """合并外部日志，自动去重（可选）+ 追加"""
        # print(len(日志列表))
        self.log_list.extend(日志列表)

    def get_logs(self) -> list:
        """
        获取最终日志列表
        ✨ 核心优化：每次提取前，自动按【时间】升序排序
        """
        if not self.debug:
            return []

        # 关键：按日志的「时间」字段排序（字符串格式可直接排序，等价于时间顺序）
        sorted_logs = sorted(self.log_list, key=lambda x: x["时间"])
        return sorted_logs

# ====================== 工具函数1：读取环境变量（统一返回结构） ======================
def 从多个变量读取第一个存在的变量值(
        变量名列表: list[str],
        # 【强制注解】仅约束：第一个参数必为str(变量值)，其余完全自由
        校验函数: Optional[Callable[[str, ...], Any]] = None,
        # 【外部自由传递】校验函数的所有额外参数（位置+关键字），无任何限制
        debug: bool = False,
        *校验函数位置参数,
        **校验函数关键字参数
) -> tuple[Optional[str], str, list]:
    """
    从环境变量列表读取第一个有效变量值
    强制返回：(变量值/None, 简要信息, 详细日志列表)
    日志规则：固定步骤 + 无索引 + 汇总记录 + 循环仅标注处理对象
    """

    logger = ToolLogger(debug)
    module = "环境变量读取"
    最终值 = None
    最终变量名 = None

    # ===================== 固定步骤1：初始化（无索引，纯文字） =====================
    logger.add(
        module=module,
        step="初始化",
        action="开始读取环境变量",
        params={"待检查变量": 变量名列表, "启用校验函数": 校验函数 is not None}
    )

    # 空列表校验
    if not 变量名列表:
        msg = "读取失败：变量名列表为空"
        logger.add(module, "初始化", "参数异常", result=msg)
        return None, msg, logger.get_logs()

    # ===================== 固定步骤2：遍历检查（无索引，循环只记当前处理对象） =====================
    logger.add(module, "变量检查", "开始遍历所有变量", params={"总变量数": len(变量名列表)})

    for 变量名 in 变量名列表:
        # 仅记录：当前在处理哪个变量，无步骤索引，无编号
        logger.add(module, "变量检查", "处理中", params={"当前变量": 变量名})

        # 变量不存在
        if 变量名 not in os.environ:
            logger.add(module, "变量检查", "跳过", params={"变量": 变量名, "原因": "不存在"})
            continue

        # 获取变量值
        变量值 = os.environ[变量名]
        logger.add(module, "变量读取", "取值成功", params={"变量": 变量名, "值长度": len(变量值)})

        # 执行校验
        if 校验函数 is not None:
            # 校验函数参数详情
            待传参数字典={}
            待传参数字典.update(校验函数关键字参数)
            待传参数字典.update(校验函数位置参数)
            待传参数字典.update({"debug":debug})
            可传参数=取安全关键字参数(校验函数,待传参数字典)




            校验结果,校验信息,校验日志 = 校验函数(变量值, **可传参数)
            logger.add(module, "变量检查", "自定义校验", params={"变量": 变量名}, result=校验结果)
            #如果返回是三个变量值后两个分别是str和list则走专用分析
            if not 校验结果:
                logger.add(module, "变量检查", "跳过", params={"变量": 变量名, "原因": "校验不通过"})
                continue
            logger.合并日志(校验日志)
            logger.add(module, "日志合并", "成功")

        # 找到第一个有效值，直接退出循环
        最终变量名 = 变量名
        最终值 = 变量值
        break

    # ===================== 固定步骤3：结果判定（无索引，汇总输出） =====================
    if 最终变量名:
        msg = f"读取成功：匹配到有效变量 [{最终变量名}]"
        logger.add(module, "结果判定", "执行成功", result=msg)
        return 最终值, msg, logger.get_logs()
    else:
        msg = "读取失败：未找到任何有效环境变量"
        logger.add(module, "结果判定", "执行失败", result=msg)
        return None, msg, logger.get_logs()

# ====================== 工具函数2：校验Git Token（统一返回结构） ======================
def 校验git和gitee_tk(tk: str, tk类型: str, debug=False) -> tuple[bool, str, list]:
    """
    极速校验GitHub/Gitee Token有效性
    强制返回：(是否有效bool, 简要信息, 详细日志列表)
    """
    logger = ToolLogger(debug)
    module = "Token校验"
    logger.add(module, "初始化", "启动校验", {"平台": tk类型, "Token长度": len(tk.strip() if tk else 0)})

    # 空Token校验
    if not tk or not tk.strip():
        msg = "校验失败：Token 为空或纯空白字符"
        logger.add(module, "步骤1", "空值检查", {}, msg)
        return False, msg, logger.get_logs()

    token = tk.strip()
    logger.add(module, "步骤1", "格式化Token", {"原始长度": len(tk)}, "完成")

    # 平台校验
    if tk类型 not in ("github", "gitee"):
        msg = f"校验失败：不支持的平台 {tk类型}"
        logger.add(module, "步骤2", "平台检查", {"输入": tk类型}, msg)
        return False, msg, logger.get_logs()
    logger.add(module, "步骤2", "平台校验通过", {}, tk类型)

    # 接口配置
    url = "https://api.github.com/user" if tk类型 == "github" else "https://gitee.com/api/v5/user"
    headers = {"Authorization": f"token {token}"}
    logger.add(module, "步骤3", "生成请求", {"URL": url}, "完成")

    # 网络请求
    logger.add(module, "步骤4", "发起请求", {"超时": 2}, "请求中")
    try:
        req = request.Request(url, headers=headers, method='GET')
        with request.urlopen(req, timeout=2) as resp:
            code = resp.getcode()
            logger.add(module, "步骤4", "请求响应", {"状态码": code}, "完成")

            if code == 200:
                msg = f"校验成功：{tk类型} Token 有效"
                logger.add(module, "结果", "校验通过", {}, msg)
                return True, msg, logger.get_logs()
            else:
                msg = f"校验失败：API返回异常状态码 {code}"
                logger.add(module, "结果", "校验失败", {}, msg)
                return False, msg, logger.get_logs()

    except error.HTTPError as e:
        msg = f"校验失败：Token无权限/已过期(码:{e.code})"
        logger.add(module, "异常", "HTTP错误", {"码": e.code}, msg)
        return False, msg, logger.get_logs()
    except (error.URLError, socket.timeout):
        msg = "校验失败：网络超时或无法连接服务器"
        logger.add(module, "异常", "网络错误", {}, msg)
        return False, msg, logger.get_logs()

# ====================== 测试入口（开箱即用） ======================
if __name__ == "__main__":
    # 配置默认环境变量名
    from 初始变量 import 默认gitee_tk变量名称,默认github_tk变量名称

    # ========== 测试1：读取环境变量（统一返回结构） ==========
    tk值, 读取信息, 读取日志 = 从多个变量读取第一个存在的变量值(默认gitee_tk变量名称, debug=True)
    print("="*60)
    print("【环境变量读取结果】")
    print(f"执行结果：{tk值}")
    print(f"简要信息：{读取信息}")
    for 日志 in 读取日志:
        print(日志)

    # ========== 测试2：校验Token（统一返回结构） ==========
    if tk值:
        校验结果, 校验信息, 校验日志 = 校验git和gitee_tk(tk值, "gitee", debug=True)
        print("="*60)
        print("【Token校验结果】")
        print(f"执行结果：{校验结果}")
        print(f"简要信息：{校验信息}")
        for 日志 in 校验日志:
            print(日志)
    else:
        print("未获取到Token，跳过校验")