# batch_public_all_final.py
import os
import urllib.request
import json
from git_sync import 帕鲁终端  # 导入你原来的脚本类
import urllib.parse
# 实例化帕鲁终端获取令牌和用户名
帕鲁 = 帕鲁终端()
令牌 = 帕鲁.令牌
用户名 = 帕鲁.用户名

# 获取账号下所有仓库（包括私有）
def 获取全部仓库(令牌):
    仓库列表 = []
    页 = 1
    每页 = 50
    头信息 = {"User-Agent": "Git-Paluh-Tool/BatchPublic/1.0"}
    while True:
        url = f"https://gitee.com/api/v5/user/repos?page={页}&per_page={每页}&access_token={令牌}"
        请求 = urllib.request.Request(url, headers=头信息)
        with urllib.request.urlopen(请求, timeout=10) as 响应:
            数据 = json.loads(响应.read().decode("utf-8"))
            if not 数据:
                break
            # 保存 owner 和 name
            仓库列表.extend([(repo["owner"]["login"], repo["name"]) for repo in 数据])
            页 += 1
    return 仓库列表

# 批量修改为公开
def 批量公开(仓库列表, 令牌):
    头信息 = {
        "User-Agent": "Git-Paluh-Tool/BatchPublic/1.0",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    for 所有者, 仓库名 in 仓库列表:
        url = f"https://gitee.com/api/v5/repos/{所有者}/{仓库名}"
        数据 = urllib.parse.urlencode({
            "name": 仓库名,
            "private": "false",   # 注意：这里用字符串 "false"
            "access_token": 令牌
        }).encode("utf-8")
        请求 = urllib.request.Request(url, data=数据, headers=头信息, method="PATCH")

        try:
            with urllib.request.urlopen(请求, timeout=30) as 响应:
                内容 = 响应.read().decode("utf-8")
                if 响应.getcode() in (200, 201):
                    print(f"[成功] {仓库名} 已改为公开")
                else:
                    print(f"[失败] {仓库名} 返回码 {响应.getcode()} 内容: {内容}")
        except urllib.error.HTTPError as e:
            错误内容 = e.read().decode("utf-8")
            print(f"[HTTP错误] {仓库名} -> {e.code} {错误内容}")
        except Exception as e:
            print(f"[错误] {仓库名} -> {e}")
# 执行
所有仓库 = 获取全部仓库(令牌)
print(f"[信息] 找到 {len(所有仓库)} 个仓库（含私有和可修改）")
批量公开(所有仓库, 令牌)