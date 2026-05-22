import os

from lib.config_mg import ConfigMg
from lib.logger import set_logger
from lib.util import 从多个变量读取第一个存在的变量值, 校验git和gitee_tk
from lib.初始变量 import 默认github_tk变量名称, 默认gitee_tk变量名称, 默认配置文件字典
from lib.git_base_api import GitHubApi as github_api, GiteeApi as gitee_api
from lib.用户配置 import 加载用户配置, 用户根目录


class MainApi:
    """
    全局 API 聚合：token、配置、日志、平台 API。
    优先使用用户级配置 (~/.gmm/config.ini)；如果显式传入 配置文件路径 也支持。
    """

    支持的平台 = ("github", "gitee")
    平台变量映射 = {
        "github": 默认github_tk变量名称,
        "gitee":  默认gitee_tk变量名称,
    }

    def __init__(self, debug: bool = False, 配置文件路径: str = None, logpath: str = None):
        self.debug = debug
        self.配置文件路径 = 配置文件路径

        # 日志：默认放在 ~/.gmm/logs/
        if logpath is None:
            logpath = os.path.join(用户根目录(), "logs")
        os.makedirs(logpath, exist_ok=True)

        self.logger = set_logger(
            level="DEBUG" if self.debug else "INFO",
            name="gmm",
            mode="console",
            path=logpath,
        )

        # 配置：显式路径优先；否则用户级配置
        if self.配置文件路径:
            self.config = ConfigMg(配置文件路径=self.配置文件路径, 默认配置文件字典=默认配置文件字典)
        else:
            self.config = 加载用户配置()

        self.tokens = {平台: None for 平台 in self.支持的平台}
        self.环境变量结果 = {}
        self.环境日志 = {}

        self.github_api = None
        self.gitee_api = None

        self.初始化()

    def 初始化(self):
        for 平台名 in self.支持的平台:
            self.初始化单个平台(平台名)

        if self.tokens.get("github"):
            self.github_api = github_api(self.tokens["github"], logger=self.logger)
        if self.tokens.get("gitee"):
            self.gitee_api = gitee_api(self.tokens["gitee"], logger=self.logger)

        self.logger.info("MainApi 初始化完成")

    def 初始化单个平台(self, 平台名: str):
        token = ""
        try:
            token = self.config.get(平台名, "token")
        except Exception:
            token = ""

        if not token or not 校验git和gitee_tk(token, tk类型=平台名)[0]:
            self.logger.warning(f"{平台名} token 配置无效，尝试从环境变量读取")
            if not self.环境变量结果:
                self.环境变量结果, _, self.环境日志 = self.从环境变量读取所有平台tk()
            token = self.环境变量结果.get(平台名)
            if self.debug and self.环境日志.get(平台名):
                for 行 in self.环境日志[平台名]:
                    self.logger.debug(行)
            if not token:
                self.logger.warning(f"{平台名} 未取到有效 token，相关 API 不可用")

        self.tokens[平台名] = token

    def 从环境变量读取所有平台tk(self):
        tk = {平台: None for 平台 in self.支持的平台}
        info = {平台: None for 平台 in self.支持的平台}
        log = {平台: None for 平台 in self.支持的平台}
        for 平台名 in tk.keys():
            变量列表 = self.平台变量映射[平台名]
            tk[平台名], info[平台名], log[平台名] = 从多个变量读取第一个存在的变量值(
                变量名列表=变量列表,
                校验函数=校验git和gitee_tk,
                debug=self.debug,
                tk类型=平台名,
            )
        return tk, info, log

    @property
    def github_tk(self):
        return self.tokens.get("github")

    @property
    def gitee_tk(self):
        return self.tokens.get("gitee")
