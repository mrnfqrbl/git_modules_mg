"""
用户级全局配置
==============
位置：~/.gmm/config.ini
内容：token、白名单域名、缓存目录等跨项目共享的配置。

与 lib/config_mg.py 的区别：
    config_mg.ConfigMg 是底层工具（自动建文件、读写键值）。
    本模块只负责确定路径并复用 ConfigMg 实例。
"""
from __future__ import annotations

import os
from typing import Optional

from lib.config_mg import ConfigMg


_默认用户配置 = {
    "github": {"token": ""},
    "gitee":  {"token": ""},
    "迁移": {
        "缓存目录":   "",                         # 留空则用 ~/.gmm/cache/
        "白名单域名": "gitee.com, openi.pcl.ac.cn",
    },
    "git": {
        "proxy": "",
        "ssl_verify": "true",
        "ssl_backend": ""
    },
}


def 用户根目录() -> str:
    """跨平台获取 ~/.gmm 的绝对路径"""
    return os.path.join(os.path.expanduser("~"), ".gmm")


def 用户配置路径() -> str:
    return os.path.join(用户根目录(), "config.ini")


def 用户缓存默认目录() -> str:
    return os.path.join(用户根目录(), "cache")


def 加载用户配置() -> ConfigMg:
    """获取/初始化用户级配置（首次调用会自动创建文件）"""
    os.makedirs(用户根目录(), exist_ok=True)
    return ConfigMg(配置文件路径=用户配置路径(), 默认配置文件字典=_默认用户配置)


def 解析缓存目录(配置: Optional[ConfigMg] = None) -> str:
    """从配置读取缓存目录；为空则返回默认值，并确保目录存在"""
    cfg = 配置 or 加载用户配置()
    try:
        值 = (cfg.get("迁移", "缓存目录") or "").strip()
    except Exception:
        值 = ""
    路径 = 值 if 值 else 用户缓存默认目录()
    os.makedirs(路径, exist_ok=True)
    return 路径


def 解析白名单域名(配置: Optional[ConfigMg] = None) -> list[str]:
    cfg = 配置 or 加载用户配置()
    try:
        原始 = cfg.get("迁移", "白名单域名") or ""
    except Exception:
        原始 = ""
    域名列表 = [d.strip() for d in 原始.split(",") if d.strip()]
    return 域名列表 or ["gitee.com", "openi.pcl.ac.cn"]
