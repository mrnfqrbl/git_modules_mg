import time

from lib.logger import NullLog
import requests
from typing import Dict, Any



class GitBaseApi:
    """Git平台API基类，定义通用接口和请求逻辑"""
    BASE_URL = ""

    def __init__(self, tk: str, logger=NullLog):
        self.tk = tk.strip()
        self.logger = logger
        self.session = requests.Session()
        # 缓存当前用户信息
        self._current_user_info = None

    def _get_headers(self) -> Dict[str, str]:
        raise NotImplementedError("子类必须实现请求头方法")

    def _send_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """通用请求发送方法（全平台统一，安全可靠）"""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        try:
            self.logger.info(f"【请求】{method} {url}")
            response = self.session.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                timeout=15,
                **kwargs
            )
            response.raise_for_status()
            return response.json() if response.content else {}

        except requests.exceptions.RequestException as e:
            err_msg = f"API请求失败: {str(e)}"
            self.logger.error(err_msg)
            # 携带响应内容，方便排查问题
            if hasattr(e, 'response') and e.response is not None:
                err_msg += f" | 响应内容: {e.response.text}"
            raise Exception(err_msg) from e

    # ==================== 核心工具方法 ====================
    def 获取当前用户信息(self) -> Dict[str, Any]:
        raise NotImplementedError("子类必须实现用户信息获取方法")

    def 获取当前用户名(self) -> str:
        """自动获取登录用户名（仓库操作必备）"""
        if not self._current_user_info:
            self._current_user_info = self.获取当前用户信息()
        return self._current_user_info["用户名"]

    # ==================== 仓库操作接口 ====================
    def 创建仓库(self, 名称: str, 描述: str = "", 私有: bool = True) -> Dict[str, Any]:
        raise NotImplementedError("子类必须实现创建仓库方法")

    def 修改仓库属性(self, 仓库名: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("子类必须实现修改仓库属性方法")

    def 获取仓库信息(self, 仓库名: str) -> Dict[str, Any]:
        raise NotImplementedError("子类必须实现获取仓库信息方法")

    def 设置仓库公开(self, 仓库名: str) -> Dict[str, Any]:
        return self.修改仓库属性(仓库名, 私有=False)

    def 设置仓库私有(self, 仓库名: str) -> Dict[str, Any]:
        return self.修改仓库属性(仓库名, 私有=True)

    def 删除仓库(self, 仓库名: str) -> Dict[str, Any]:
        raise NotImplementedError("子类必须实现删除仓库方法")

    # ==================== 通用便捷方法 ====================
    def 仓库是否存在(self, 仓库名: str) -> bool:
        """判断当前用户下是否存在指定名称的仓库(只判存在,不抛)。"""
        try:
            self.获取仓库信息(仓库名)
            return True
        except Exception:
            return False

    def 查找可用仓库名(self, 基础名称: str, 最大尝试: int = 50) -> str:
        """
        在当前用户下为 基础名称 找一个可用名。
        若基础名已被占用,尝试 基础名_1、基础名_2...,直到找到可用的或超过尝试次数。
        """
        if not self.仓库是否存在(基础名称):
            return 基础名称
        for i in range(1, 最大尝试 + 1):
            候选 = f"{基础名称}_{i}"
            if not self.仓库是否存在(候选):
                return 候选
        raise RuntimeError(f"在 {最大尝试} 次尝试内未找到可用仓库名(基础:{基础名称})")

    def 获取最新提交(self, 仓库名: str) -> Dict[str, Any]:
        """获取当前用户下指定仓库默认分支的最新一条提交信息"""
        try:
            用户名 = self.获取当前用户名()
            原始数据 = self._send_request("GET", f"repos/{用户名}/{仓库名}/commits", params={"per_page": 1})
            if 原始数据 and isinstance(原始数据, list) and len(原始数据) > 0:
                item = 原始数据[0]
                return {
                    "sha": item.get("sha", ""),
                    "message": item.get("commit", {}).get("message", "")
                }
        except Exception:
            pass
        return {}

    def 获取历史提交列表(self, 仓库名: str, 数量: int = 100) -> list[Dict[str, Any]]:
        """获取当前用户下指定仓库默认分支的历史提交列表"""
        try:
            用户名 = self.获取当前用户名()
            原始数据 = self._send_request("GET", f"repos/{用户名}/{仓库名}/commits", params={"per_page": 数量})
            if 原始数据 and isinstance(原始数据, list):
                result = []
                for item in 原始数据:
                    if isinstance(item, dict):
                        result.append({
                            "sha": item.get("sha", ""),
                            "message": item.get("commit", {}).get("message", "")
                        })
                return result
        except Exception:
            pass
        return []

    def 获取文件内容(self, 仓库名: str, 路径: str) -> str:
        """获取当前用户下指定仓库中某个文件的内容（Base64解码后返回字符串）"""
        try:
            用户名 = self.获取当前用户名()
            原始数据 = self._send_request("GET", f"repos/{用户名}/{仓库名}/contents/{路径}")
            if isinstance(原始数据, dict) and "content" in 原始数据:
                import base64
                content = 原始数据["content"]
                # 兼容返回内容中有换行符等特殊情况
                content = "".join(content.split())
                decoded_bytes = base64.b64decode(content)
                return decoded_bytes.decode("utf-8")
        except Exception:
            pass
        return ""


class GitHubApi(GitBaseApi):
    """GitHub API实现类（标准请求头认证）"""
    BASE_URL = "https://api.github.com"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"token {self.tk}",
            "Accept": "application/vnd.github.v3+json"
        }

    def 获取当前用户信息(self) -> Dict[str, Any]:
        原始数据 = self._send_request("GET", "user")
        return {
            "用户名": 原始数据["login"],
            "用户ID": 原始数据["id"],
            "头像地址": 原始数据["avatar_url"],
            "邮箱": 原始数据.get("email", "未设置"),
            "公开仓库数": 原始数据["public_repos"]
        }

    def 创建仓库(self, 名称: str, 描述: str = "", 私有: bool = False, 自动初始化: bool = False) -> Dict[str, Any]:
        data = {"name": 名称, "description": 描述, "private": 私有, "auto_init": int(自动初始化)}
        原始数据 = self._send_request("POST", "user/repos", json=data)
        return {
            "成功": True,
            "仓库名": 原始数据["name"],
            "仓库ID": 原始数据["id"],
            "仓库地址": 原始数据["html_url"],
            "私有状态": 原始数据["private"],
            "描述": 原始数据.get("description", "")
        }

    def 获取仓库信息(self, 仓库名: str) -> Dict[str, Any]:
        用户名 = self.获取当前用户名()
        原始数据 = self._send_request("GET", f"repos/{用户名}/{仓库名}")
        return {
            "仓库名": 原始数据["name"],
            "仓库ID": 原始数据["id"],
            "仓库地址": 原始数据["html_url"],
            "私有状态": 原始数据["private"],
            "描述": 原始数据.get("description", ""),
            "星标数": 原始数据["stargazers_count"],
            "分支数": 原始数据["forks_count"]
        }

    def 修改仓库属性(self, 仓库名: str, **kwargs) -> Dict[str, Any]:
        用户名 = self.获取当前用户名()
        if "私有" in kwargs:
            kwargs["private"] = kwargs.pop("私有")
        原始数据 = self._send_request("PATCH", f"repos/{用户名}/{仓库名}", json=kwargs)
        return {
            "成功": True,
            "仓库名": 原始数据["name"],
            "修改后属性": {k: v for k, v in kwargs.items()}
        }

    def 删除仓库(self, 仓库名: str) -> Dict[str, Any]:
        用户名 = self.获取当前用户名()
        self._send_request("DELETE", f"repos/{用户名}/{仓库名}")
        return {
            "成功": True,
            "消息": f"仓库【{仓库名}】已成功删除"
        }




class GiteeApi(GitBaseApi):
    """Gitee API实现类（修复导入接口 + 纯请求头安全认证）"""
    BASE_URL = "https://gitee.com/api/v5"

    def _get_headers(self) -> Dict[str, str]:
        # Gitee 官方标准请求头，与GitHub对齐
        return {
            "Authorization": f"token {self.tk}",
            "Content-Type": "application/json"
        }

    def 获取当前用户信息(self) -> Dict[str, Any]:
        原始数据 = self._send_request("GET", "user")
        return {
            "用户名": 原始数据["login"],
            "用户ID": 原始数据["id"],
            "头像地址": 原始数据["avatar_url"],
            "邮箱": 原始数据.get("email", "未设置"),
            "公开仓库数": 原始数据["public_repos"]
        }
    # TODO: gitee貌似限制个人用户创建仓库只能私有
    def 创建仓库(self, 名称: str, 描述: str = "", 私有: bool = False, 自动初始化: bool = False) -> Dict[str, Any]:
        data = {"name": 名称,
                "description": 描述,
                "public": int(not 私有),
                "auto_init": int(自动初始化),}
        原始数据 = self._send_request("POST", "user/repos", json=data)
        # #如果原始数据中public=false 则调用self.设置仓库公开
        # if not 原始数据["public"]:
        #     返回=self.设置仓库公开(原始数据["name"])
        #     原始数据["public"] = 返回["修改后属性"]=

        return {
            "成功": True,
            "仓库名": 原始数据["name"],
            "仓库ID": 原始数据["id"],
            "仓库地址": 原始数据["html_url"],
            "公开状态": 原始数据["public"],
            "描述": 原始数据.get("description", "")
        }

    def 获取仓库信息(self, 仓库名: str) -> Dict[str, Any]:
        用户名 = self.获取当前用户名()
        原始数据 = self._send_request("GET", f"repos/{用户名}/{仓库名}")
        return {
            "仓库名": 原始数据["name"],
            "仓库ID": 原始数据["id"],
            "仓库地址": 原始数据["html_url"],
            "私有状态": 原始数据["private"],
            "描述": 原始数据.get("description", ""),
            "星标数": 原始数据["stargazers_count"],
            "分支数": 原始数据["forks_count"]
        }

    def 修改仓库属性(self, 仓库名: str, **kwargs) -> Dict[str, Any]:
        用户名 = self.获取当前用户名()
        if "name" not in kwargs and "名称" not in kwargs:
            kwargs["name"] = 仓库名
        if "私有" in kwargs:
            kwargs["private"] = int(kwargs.pop("私有"))
        原始数据 = self._send_request("PATCH", f"repos/{用户名}/{仓库名}", json=kwargs)
        return {
            "成功": True,
            "仓库名": 原始数据["name"],
            "修改后属性": {k: v for k, v in kwargs.items()}
        }

    def 删除仓库(self, 仓库名: str) -> Dict[str, Any]:
        用户名 = self.获取当前用户名()
        self._send_request("DELETE", f"repos/{用户名}/{仓库名}")
        return {
            "成功": True,
            "消息": f"仓库【{仓库名}】已成功删除"
        }

if __name__ == '__main__':
    pass
    # # 配置你的Token
    #
    # REPO_NAME = "test_0002"
    #
    # # 测试 GitHub
    # try:
    #     # github = GitHubApi(GITHUB_TOKEN)
    #     # github.创建仓库(REPO_NAME, 描述="测试仓库")
    #     # print(f"GitHub 仓库 {REPO_NAME} 创建成功")
    #     #
    #     # repo = github.获取仓库信息(REPO_NAME)
    #     # print(f"GitHub 仓库信息：{repo}")
    #
    #     # github.删除仓库(REPO_NAME)
    #     # print(f"GitHub 仓库 {REPO_NAME} 删除成功")
    # except Exception as e:
    #     raise e
    #
    # # 测试源仓库使用你提供的 GitHub 地址
    # TEST_SOURCE_REPO = "https://github.com/mrnfqrbl/obj2dict"
    # TEST_REPO_BASE = "obj2dict_test"
    #
    #
    # try:
    #     # gitee = GiteeApi(GITEE_TOKEN)
    #     print(">>> 开始测试 GiteeApi 全函数 <<<\n")
    #
    #     # ==========================================================================
    #     # 1. 测试：创建仓库
    #     # ==========================================================================
    #     print(f"1. 测试创建仓库: {TEST_REPO_BASE}")
    #     create_result = gitee.创建仓库(TEST_REPO_BASE, 描述="这是一个用于全功能测试的仓库", 私有=True, 自动初始化=True)
    #     print(f"   ✅ 创建成功: {create_result.get('html_url', '无链接')}\n")
    #
    #     # # ==========================================================================
    #     # # 2. 测试：获取仓库信息
    #     # # ==========================================================================
    #     print(f"2. 测试获取仓库信息: {TEST_REPO_BASE}")
    #     repo_info = gitee.获取仓库信息(TEST_REPO_BASE)
    #     print(f"   ✅ 获取成功: 仓库ID={repo_info.get('id')}, 私有={repo_info.get('private')}\n")
    #
    #     # ==========================================================================
    #     # 3. 测试：修改仓库属性
    #     # # ==========================================================================
    #     print(f"3. 测试修改仓库属性: {TEST_REPO_BASE} (改为公开)")
    #     update_result = gitee.修改仓库属性(TEST_REPO_BASE, 私有=False, description="已修改描述")
    #     print(f"   ✅ 修改成功\n")
    #     d=gitee.删除仓库(TEST_REPO_BASE)
    #     print(f"   ✅ 删除成功\n")
    #
    #
    # except Exception as e:
    #     print(f"❌ 测试过程中发生致命错误: {str(e)}")
    #     import traceback
    #     traceback.print_exc()
    # except Exception as e:
    #     raise e