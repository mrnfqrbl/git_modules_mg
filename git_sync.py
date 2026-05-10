import os
import re
import subprocess
import urllib.request
import json
import shutil
import time
import sys
from concurrent.futures import ThreadPoolExecutor

# ================= 配置区域 =================
配置 = {
    "白名单域名": ["gitee.com", "openi.pcl.ac.cn"],
    "子仓库白名单": ["custom_nodes\\com_mrnf_node", "com_frontend"],
    "依赖文件名": ["requirements.txt", "setup.py", "pyproject.toml"],
    "报告文件名": "审计报告",
    "最大校验线程": 15
}

class 帕鲁终端:
    def __init__(self):
        self.令牌 = self.获取令牌()
        self.用户名 = self.校验身份()
        self.已处理映射 = {}
        self.记录集 = {}      # 路径 -> 模式
        self.依赖追踪 = {}    # 仓库路径 -> [{文件, 原始, 目标, 状态}]
        self.顶级目录 = os.path.abspath(os.getcwd())

    def 获取令牌(self):
        令牌 = os.environ.get("GITEE_TOKEN")
        if not 令牌:
            令牌 = input("[系统] 请输入 Gitee 令牌: ").strip()
        if not 令牌: sys.exit(1)
        return 令牌

    def 校验身份(self):
        码, 响应 = self.调用API("/user")
        if 码 != 200: sys.exit(1)
        print(f"[系统] 身份校验成功，当前用户: {响应.get('login')}")
        return 响应.get("login")

    def 调用API(self, 终点, 方法="GET", 提交数据=None):
        网址 = f"https://gitee.com/api/v5{终点}"
        头信息 = {"User-Agent": "Git-Paluh-Tool/18.0", "Content-Type": "application/json"}
        最终URL = 网址 if 方法 == "POST" else f"{网址}?access_token={self.令牌}"
        try:
            请求 = urllib.request.Request(
                最终URL, data=json.dumps(提交数据).encode('utf-8') if 提交数据 else None,
                headers=头信息, method=方法
            )
            with urllib.request.urlopen(请求, timeout=10) as 响应:
                return 响应.getcode(), json.loads(响应.read().decode('utf-8'))
        except Exception as e: return 500, str(e)

    def 执行(self, 指令, 目录=None):
        try:
            结果 = subprocess.run(指令, shell=True, cwd=目录, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            return 结果.returncode == 0, 结果.stdout.strip(), 结果.stderr.strip()
        except Exception as e: return False, "", str(e)

    def 镜像到码云(self, 原始地址):
        原始地址 = 原始地址.strip().strip("'").strip('"')
        if not 原始地址 or any(域 in 原始地址 for 域 in 配置["白名单域名"]): return 原始地址
        if 原始地址 in self.已处理映射: return self.已处理映射[原始地址]

        print(f"[镜像] 开始搬运 -> {原始地址}")
        仓库名 = re.sub(r'[^\w\-_]', '_', 原始地址.rstrip('/').split('/')[-1].replace('.git', ''))
        目标地址 = f"https://gitee.com/{self.用户名}/{仓库名}.git"
        推送地址 = f"https://oauth2:{self.令牌}@gitee.com/{self.用户名}/{仓库名}.git"

        # 尝试在Gitee创建仓库
        self.调用API("/user/repos", 方法="POST", 提交数据={"name": 仓库名, "private": False})
        print(f"[镜像] 创建仓库 -> {目标地址}")
        临时 = f".tmp_paluh_{int(time.time()*1000)}"
        成功, _, _ = self.执行(f"git clone --bare \"{原始地址}\" {临时}")
        if not 成功:
            print(f"[镜像] 创建仓库失败 -> {目标地址}")
            return 原始地址

        if 成功:
            self.执行(f"git push --mirror \"{推送地址}\"", 目录=临时)
            shutil.rmtree(临时, ignore_errors=True)
            self.已处理映射[原始地址] = 目标地址
            print(f"[镜像] 完成 -> {目标地址}")
            return 目标地址

        return 原始地址

    def 核心递归(self, 当前目录, 当前归属仓库=None):
        绝对 = os.path.abspath(当前目录)
        相对 = os.path.relpath(绝对, self.顶级目录)

        # 判定归属仓库
        if 绝对 == self.顶级目录 or 相对 in 配置["子仓库白名单"]:
            归属 = 绝对
        else:
            归属 = 当前归属仓库 if 当前归属仓库 else self.顶级目录

        模式 = "手动" if (绝对 == self.顶级目录 or os.path.basename(绝对) in 配置["子仓库白名单"] or 相对 in 配置["子仓库白名单"]) else "自动"
        self.记录集[绝对] = 模式

        print(f"\n[处理] {模式}模式 | 归属:{os.path.basename(归属)} -> {绝对}")

        # 预先同步以防止游离状态
        self.执行("git submodule sync", 目录=当前目录)
        self.执行("git submodule update --init", 目录=当前目录)

        子路径列表 = []
        gitmodules_path = os.path.join(当前目录, ".gitmodules")







        # ================= 核心优化：子模块索引动态管理 =================

        if os.path.exists(gitmodules_path):
            成, 输出, _ = self.执行("git config -f .gitmodules --get-regexp path", 目录=当前目录)
            if 成 and 输出:
                for 行 in 输出.splitlines():
                    try:
                        键, p = 行.split(' ', 1)
                        # 提取 submodule 的具体 name (键的格式如: submodule.模块名.path)
                        子模块名 = 键.split('.')[1]
                        网址键 = f"submodule.{子模块名}.url"

                        成2, 旧URL, _ = self.执行(f"git config -f .gitmodules --get {网址键}", 目录=当前目录)
                        if 成2 and 旧URL:
                            子路径列表.append(p)
                            新URL = self.镜像到码云(旧URL)

                            if 新URL != 旧URL:
                                print(f"  [子模块] 检测到链接变更, 自动更新索引: {p}")
                                # 1. 替换配置文件中的URL并添加到索引
                                self.执行(f"git config -f .gitmodules {网址键} \"{新URL}\"", 目录=当前目录)
                                self.执行("git add .gitmodules", 目录=当前目录)

                                # 2. 同步子模块新链接到 .git/config
                                self.执行(f"git submodule sync \"{p}\"", 目录=当前目录)

                                # 3. 重新初始化并拉取新仓库内容
                                self.执行(f"git submodule update --init \"{p}\"", 目录=当前目录)

                                # 4. 关键需求：根据物理存在状态，自动在Git索引中新增或删除子仓库
                                物理路径 = os.path.join(当前目录, p)
                                if os.path.exists(物理路径) and os.path.exists(os.path.join(物理路径, ".git")):
                                    self.执行(f"git add \"{p}\"", 目录=当前目录)
                                    print(f"  [索引] ✅ 已将子仓库 '{p}' 变更新增至 git index")
                                else:
                                    self.执行(f"git rm --cached \"{p}\"", 目录=当前目录)
                                    print(f"  [索引] 🗑️ 子仓库 '{p}' 失效/不存在，已从 git index 移除")
                    except Exception as e:
                        print(f"  [警告] 解析子模块记录失败: {行} | 错误: {e}")

        # ================= 扫描并替换依赖文件 =================
        for f_name in 配置["依赖文件名"]:
            f_path = os.path.join(当前目录, f_name)
            if os.path.exists(f_path):
                if self.替换文件(f_path, 归属):
                    # 无论什么模式，修改了都加入索引
                    self.执行(f"git add \"{f_name}\"", 目录=当前目录)
                    print(f"  [依赖] 更新并暂存 -> {f_name}")

        # ================= 递归深入子模块 =================
        for p in 子路径列表:
            sub_p = os.path.join(当前目录, p)
            if os.path.isdir(sub_p):
                self.核心递归(sub_p, 归属)

                # ================= 提交代码 =================
        if 模式 == "自动":
            _, 状态, _ = self.执行("git status --short", 目录=当前目录)
            if 状态.strip():
                self.执行("git commit -m 'chore: 帕鲁自动化搬运与索引重构'", 目录=当前目录)
                self.执行("git push", 目录=当前目录)
                print(f"  [提交] ✅ 自动处理完成并已 Push")

    def 替换文件(self, 路径, 归属仓库):
        try:
            with open(路径, 'r', encoding='utf-8', errors='ignore') as f: 内容 = f.read()
            # 优化正则：排除 pyproject.toml 常见的逗号、圆括号闭合
            正则 = r'(git\+https?://[^\s\'"<>#,\)]+|git@[^\s\'"<>#,\)]+|https?://github\.com/[^\s\'"<>#,\)]+\.git)'
            匹配 = list(set(re.findall(正则, 内容)))
            修改 = False

            if 归属仓库 not in self.依赖追踪: self.依赖追踪[归属仓库] = []

            for 项 in 匹配:
                纯URL = 项.replace('git+', '')
                新URL = self.镜像到码云(纯URL)
                成功 = (新URL != 纯URL and "gitee.com" in 新URL)

                self.依赖追踪[归属仓库].append({
                    "文件": os.path.relpath(路径, self.顶级目录),
                    "原始": 项,
                    "目标": 项.replace(纯URL, 新URL),
                    "状态": "成功" if 成功 else "跳过/已在白名单"
                })

                if 成功:
                    内容 = 内容.replace(项, 项.replace(纯URL, 新URL))
                    修改 = True

            if 修改:
                with open(路径, 'w', encoding='utf-8') as f: f.write(内容)
                return True
        except Exception as e:
            print(f"  [警告] 替换文件失败 {路径}: {e}")
        return False

    def 并行审计(self):
        print(f"\n[审计] 正在生成报告数据...")
        结果 = []
        with ThreadPoolExecutor(max_workers=配置["最大校验线程"]) as pool:
            任务 = [pool.submit(self.校验节点, p) for p in self.记录集.keys()]
            for t in 任务: 结果.append(t.result())
        return 结果

    def 校验节点(self, 路径):
        模式 = self.记录集[路径]
        报告 = {"路径": 路径, "模式": 模式, "本地": "✅ 正常", "远程": "➖ N/A", "依赖": "✅ 清理完成", "明细": []}

        if 路径 in self.依赖追踪:
            报告["明细"] = self.依赖追踪[路径]

        if 路径 != self.顶级目录:
            成, url, _ = self.执行("git remote get-url origin", 目录=路径)
            if 成:
                验证URL = url
                if "gitee.com" in url:
                    验证URL = url.replace("https://gitee.com/", f"https://oauth2:{self.令牌}@gitee.com/")
                探测成功, 输出, _ = self.执行(f"git ls-remote --heads \"{验证URL}\"")
                if 探测成功:
                    报告["远程"] = "✅ 存在且非空" if 输出.strip() else "⚠️ 仓库为空"
                else: 报告["远程"] = "❌ 访问失败"

        return 报告

    def 生成报告(self, 结果):
        json_名 = 配置["报告文件名"] + ".json"
        with open(json_名, 'w', encoding='utf-8') as f:
            json.dump(结果, f, ensure_ascii=False, indent=4)

        html_名 = 配置["报告文件名"] + ".html"
        表格行 = ""
        for d in 结果:
            if not d["明细"] and d["远程"] == "➖ N/A" and d["路径"] != self.顶级目录 and d["模式"] != "手动":
                continue

            模式色 = "color:#0078d4" if d["模式"] == "手动" else "color:#27ae60"
            远程色 = "color:green" if "✅" in d["远程"] else ("color:orange" if "⚠️" in d["远程"] else "color:red")

            依赖详情html = "<ul>"
            for item in d["明细"]:
                色 = "green" if item["状态"] == "成功" else "gray"
                依赖详情html += f"<li style='font-size:11px;color:{色}'><b>[{item['文件']}]</b><br>{item['原始']}</li>"
            依赖详情html += "</ul>" if d["明细"] else "无"

            表格行 += f"""
            <tr>
                <td style="font-size:12px">{d['路径']}</td>
                <td style="{模式色};font-weight:bold">{d['模式']}</td>
                <td>{d['本地']}</td>
                <td style="{远程色}">{d['远程']}</td>
                <td>{依赖详情html}</td>
            </tr>"""

        模板 = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>审计报告</title>
        <style>body{{font-family:sans-serif;margin:20px;background:#f8f9fa}} 
        table{{width:100%;border-collapse:collapse;background:#fff;table-layout:fixed;word-break:break-all}} 
        th,td{{padding:10px;border:1px solid #dee2e6;text-align:left;vertical-align:top}} 
        th{{background:#343a40;color:#fff}}</style></head>
        <body><h2>🚀 帕鲁自动迁移审计报告 (v18.0 索引追踪版)</h2>
        <table><thead><tr><th width="20%">路径</th><th width="8%">模式</th><th width="8%">本地</th><th width="15%">远程(ls-remote)</th><th width="49%">依赖迁移明细</th></tr></thead>
        <tbody>{表格行}</tbody></table></body></html>"""

        with open(html_名, 'w', encoding='utf-8') as f: f.write(模板)
        print(f"\n[完成] 报告已生成！请查看 {html_名}")

    def 启动(self):
        self.核心递归(self.顶级目录)
        结果 = self.并行审计()
        self.生成报告(结果)

if __name__ == "__main__":
    帕鲁 = 帕鲁终端()
    帕鲁.启动()