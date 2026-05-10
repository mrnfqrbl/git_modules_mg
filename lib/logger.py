import os
import sys

from loguru import logger

def set_logger(level="INFO", name="git_modules_mg", mode="console", path=None):
    """
    设置日志记录器（优化版）
    :param level: 日志级别 INFO/DEBUG/WARNING/ERROR
    :param name: 日志文件名前缀
    :param mode: console(仅控制台) | file(仅文件) | all(控制台+文件)
    :param path: 日志文件保存目录（mode=file/all 时必填）
    :return: logger 实例
    """
    # 1. 清空原有日志处理器（核心保留）
    logger.remove()


    # 3. 核心逻辑：判断是否需要输出【文件日志】
    # 条件：模式为file/all + 路径存在且有效
    enable_file = False
    if mode in ("file", "all"):
        if path and os.path.isdir(path):
            enable_file = True
        else:
            # 路径无效，自动降级为控制台输出
            print(f"警告：日志路径无效，{mode}模式自动切换为控制台模式")

    # 4. 按模式添加日志输出
    if mode == "file" and enable_file:
        # 仅文件输出
        log_file = os.path.join(path, f"{name}.log")
        logger.add(log_file, level=level)
    else:
        # 所有其他情况：必加控制台输出
        logger.add(sys.stdout, level=level)
        # all模式 + 路径有效：额外加文件输出
        if mode == "all" and enable_file:
            log_file = os.path.join(path, f"{name}.log")
            logger.add(log_file, level=level)

    # 5. 绑定日志名称并返回
    logger.bind(name=name)
    return logger






class NullLog:
    # 捕获所有未定义的方法/属性，返回空函数（支持任意参数）
    def __getattr__(self, name):
        return lambda *args, **kwargs: None

    # 支持实例直接调用：log("msg")
    def __call__(self, *args, **kwargs):
        pass
NullLog=NullLog()
