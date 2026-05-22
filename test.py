import os

from git import Repo, Submodule, Git

from lib.main_api import MainApi

import time
import cProfile
import pstats
from io import StringIO

# ---------------------- 【导入你的原有类】 ----------------------
# 请根据你的实际路径导入 MainApi
# from your_module import MainApi


tkapi = MainApi()
github_tk = tkapi.github_tk
github_api = tkapi.github_api
gitee_api=tkapi.gitee_api
# 🔥 这是实际执行耗时的核心方法
user_info = github_api.获取当前用户信息()
print(user_info)


# repo1=Repo("D:\\temp\\test1")
# repo2=Repo("D:\\temp\\test2")
# branch1=repo1.active_branch.name
# branch2=repo2.active_branch.name
# #
# # repo1.create_remote("origin", "https://github.com/mrnfqrbl/test1.git")
# # repo2.create_remote("origin", "https://github.com/mrnfqrbl/test2.git")
# readme_path = os.path.join(repo2.working_dir, "README.md")
# with open(readme_path, "w", encoding="utf-8") as f:
#     f.write("# test2\n子模块仓库,a11av1aa")
#
# readme_path = os.path.join(repo1.working_dir, "README.md")
# with open(readme_path, "w", encoding="utf-8") as f:
#     f.write("# test1\n子模块仓库,bb111vbbb")
# #提交仓库2并推送
# repo2.git.add(".")
#
# repo2.git.commit("-m", "first commit")
# #获取仓库2当前分支
#
#
#
# repo2.git.push("-u","origin", branch2)
# print("第一次push仓库2完成")
# repo1.git.add(".")
# #给仓库1添加子仓库url为https://github.com/mrnfqrbl/test2.git，路径为 com/t2
# Submodule.add(repo1,name="t2", url="https://github.com/mrnfqrbl/test2.git", path="com/t2")
# print("添加子仓库com/t2完成")
# repo1.git.commit("-m", "add submodule com/t2")
# repo1.git.push("-u","origin", branch1)
# print("第一次push仓库1完成")
