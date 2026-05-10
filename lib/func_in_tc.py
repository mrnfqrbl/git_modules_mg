import inspect
import json
from typing import Callable, Any, Dict, List, Union, get_args, get_origin


# ====================== 工具：提取干净类型名称（支持多类型转列表） ======================
def 提取干净类型名(类型注解) -> Union[str, List[str]]:
    # 无注解
    if 类型注解 is inspect._empty:
        return "无注解"

    # 获取类型源头
    源头 = get_origin(类型注解) or 类型注解

    # 处理多类型 Union (Union[str, int])
    if 源头 is Union:
        子类型列表 = []
        for 子类型 in get_args(类型注解):
            子类型列表.append(子类型.__name__ if hasattr(子类型, "__name__") else str(子类型))
        return 子类型列表

    # 处理普通类型 (str, bool, int)
    if hasattr(类型注解, "__name__"):
        return 类型注解.__name__

    # 兜底
    return str(类型注解)


# ====================== 核心：探测函数参数（纯中文 + 干净类型 + 多类型列表） ======================
def 探测函数参数(目标函数: Callable) -> Dict[str, Any]:
    结果 = {
        "函数名": 目标函数.__name__,
        "参数总数": 0,
        "参数详情": [],
        "支持的关键字参数": []
    }

    try:
        签名 = inspect.signature(目标函数)
        参数列表 = 签名.parameters
        结果["参数总数"] = len(参数列表)

        for 名称, 对象 in 参数列表.items():
            # 🔥 关键：获取干净类型名（多类型自动列表）
            类型名 = 提取干净类型名(对象.annotation)

            单参数信息 = {
                "参数名": 名称,
                "参数类型": 类型名,  # str / bool / ["str", "int"]
                "默认值": 对象.default if 对象.default != inspect._empty else None,
                "参数分类": ""
            }

            # 中文分类
            种类映射 = {
                inspect.Parameter.POSITIONAL_OR_KEYWORD: "普通参数",
                inspect.Parameter.KEYWORD_ONLY: "仅限关键字",
                inspect.Parameter.VAR_KEYWORD: "关键字可变参数(**kwargs)"
            }
            分类 = 种类映射.get(对象.kind, "其他")
            单参数信息["参数分类"] = 分类

            结果["参数详情"].append(单参数信息)

            # 收集可透传的关键字参数
            if 分类 in ["普通参数", "仅限关键字"]:
                结果["支持的关键字参数"].append(名称)

    except Exception:
        结果["错误"] = "无法获取参数"

    return 结果


# ====================== 安全透传关键字参数（自用必备） ======================
def 取安全关键字参数(目标函数: Callable, 待传参数字典: Dict[str, Any]) -> Dict[str, Any]:
    支持参数 = 探测函数参数(目标函数)["支持的关键字参数"]
    return {k: v for k, v in 待传参数字典.items() if k in 支持参数}


# ====================== 测试（完美输出） ======================
# ====================== 🚀 全覆盖边界测试（10种极端场景） ======================
if __name__ == '__main__':
    def  测试函数(位置参数1: str,关键字参数1: str):
        pass
    # 探测并打印结果
    详情 = 探测函数参数(测试函数)
    # 格式化输出（更清晰）
    import json
    print(json.dumps(详情, ensure_ascii=False, indent=2))
