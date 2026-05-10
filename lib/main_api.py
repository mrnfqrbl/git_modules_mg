import os

from lib.config_mg import ConfigMg
from lib.logger import set_logger
from lib.util import 从多个变量读取第一个存在的变量值,校验git和gitee_tk
from lib.初始变量 import 默认github_tk变量名称,默认gitee_tk变量名称,默认配置文件字典
from lib.git_base_api import GitHubApi as github_api, GiteeApi as gitee_api
from lib.git_command import Git工具
class MainApi:
    # ====================== 【核心优化】定义支持的平台（唯一写死的地方） ======================
    # 后续新增平台：只在这里加字符串，比如 "gitlab"
    支持的平台 = ("github", "gitee")
    # 平台对应环境变量配置映射
    平台变量映射 = {
        "github": 默认github_tk变量名称,
        "gitee": 默认gitee_tk变量名称
    }

    def __init__(self,debug=False,配置文件路径=None,logpath=None,rootdir=None):
        self.配置文件路径=配置文件路径
        self.rootdir=rootdir
        self.debug=debug
        if self.rootdir is None:
            self.root=os.path.dirname(os.path.dirname(__file__))
        if self.配置文件路径 is None:
            self.配置文件路径=os.path.join(self.root,"config.ini")
        if logpath is None:
            logpath=os.path.join(self.root,"logs")

        self.logger=set_logger(level="DEBUG" if self.debug else "INFO", name="git_modules_mg", mode="console", path=logpath)
        self.config=ConfigMg(配置文件路径=self.配置文件路径,默认配置文件字典=默认配置文件字典)
        self.git工具=Git工具()
        # 用字典统一存储所有平台Token（替代单独的属性）
        self.tokens = {平台: None for 平台 in self.支持的平台}
        # 环境变量缓存
        self.环境变量结果 = {}
        self.环境日志 = {}

        self.初始化()

    def 初始化(self):
        # 【核心优化】循环处理所有平台，不用分别写github/gitee
        for 平台名 in self.支持的平台:
            self.初始化单个平台(平台名)

        if "github" in self.tokens.keys() and self.tokens["github"]:
            self.github_api=github_api(self.tokens["github"])
        if "gitee" in self.tokens.keys() and self.tokens["gitee"]:
            self.gitee_api=gitee_api(self.tokens["gitee"])


        self.logger.info("初始化完成")

    def 初始化单个平台(self, 平台名):
        """【公共方法】初始化单个平台的Token（所有平台共用一套逻辑）"""
        # 1. 从配置文件读取
        token = self.config.get(平台名, "token")
        # 2. 校验Token
        if not token or not 校验git和gitee_tk(token):
            self.logger.warning(f"{平台名} token 无效，尝试从环境变量读取")

            # 首次读取环境变量（只读一次，缓存结果）
            if not self.环境变量结果:
                self.环境变量结果, _, self.环境日志 = self.从环境变量读取所有平台tk()

            # 从缓存中获取对应平台的Token
            token = self.环境变量结果[平台名]
            # 打印调试日志
            if self.debug and self.环境日志[平台名]:
                for i in self.环境日志[平台名]:
                    self.logger.debug(i)

            if not token:
                self.logger.error(f"跳过 {平台名} token ，默认配置tk无效，且未从环境变量读取到")

        # 赋值到统一字典
        self.tokens[平台名] = token



    def 从环境变量读取所有平台tk(self):
        """【公共方法】批量读取所有平台的环境变量Token"""
        tk = {平台: None for 平台 in self.支持的平台}
        info = {平台: None for 平台 in self.支持的平台}
        log = {平台: None for 平台 in self.支持的平台}

        for 平台名 in tk.keys():
            变量列表 = self.平台变量映射[平台名]
            tk[平台名], info[平台名], log[平台名] = 从多个变量读取第一个存在的变量值(
                变量名列表=变量列表,
                校验函数=校验git和gitee_tk,
                debug=self.debug,
                tk类型=平台名
            )
        return tk, info, log
    @property
    def github_tk(self):
        return self.tokens["github"]

    @property
    def gitee_tk(self):
        return self.tokens["gitee"]







if __name__ == "__main__":
    api=MainApi(debug=False)

    print(api.tokens)
    创建仓库结果= api.gitee_api.创建仓库("test_repo",自动初始化=True,私有=True)
    print(创建仓库结果)
    获取仓库信息= api.gitee_api.获取仓库信息("test_repo")
    print(获取仓库信息)
    修改仓库信息= api.gitee_api.修改仓库属性("test_repo",描述="这是一个测试仓库",私有=False)
    print(修改仓库信息)
    获取仓库信息= api.gitee_api.获取仓库信息("test_repo")
    print(获取仓库信息)
    删除仓库结果= api.gitee_api.删除仓库("test_repo")
    print(删除仓库结果)
