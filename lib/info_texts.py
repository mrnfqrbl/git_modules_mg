"""
帮助文本原子化管理（v2）
========================
所有帮助信息拆分为最小单元，方便组合、复用、维护。

结构：
  - 元信息：工具名、版本、简介
  - 命令定义：每个命令的各个组成部分独立存储
  - 模板：组合原子单元生成最终输出
  - 错误提示：独立管理
"""

# ═══════════════════════════════════════════════════════════
# 元信息
# ═══════════════════════════════════════════════════════════
META = {
    "name": "gmm",
    "full_name": "Git Modules Manager",
    "version": "2.0.0",
    "brief": "Git 子模块批量迁移工具（GitHub -> Gitee）",
}

# ═══════════════════════════════════════════════════════════
# 命令分类标记
# ═══════════════════════════════════════════════════════════
# need_repo: True  = 需要根仓库上下文（在仓库目录或用 gmm <仓库名> <命令>）
#            False = 不需要（可直接 gmm <命令>）
# has_sub_help: True  = 子命令还有 -h 子帮助
#               False = 子命令没有再嵌套子命令

# ═══════════════════════════════════════════════════════════
# 命令原子定义
# ═══════════════════════════════════════════════════════════
COMMANDS = {

    "add": {
        "brief": "添加仓库到迁移清单",
        "usage": "gmm add <url> [<url2> ...] [选项]",
        "need_repo": True,
        "has_sub_help": False,
        "usage_formats": [
            ("gmm add <url>", "在当前仓库目录下执行"),
            ("gmm <仓库名> add <url>", "指定已注册仓库执行"),
        ],
        "desc": "将 GitHub 等平台仓库 URL 加入待迁移清单。执行 gmm run 时会镜像到 Gitee。",
        "args": [
            ("<url>", "仓库地址，如 https://github.com/user/repo.git"),
        ],
        "opts": [
            ("--name <名称>", "指定子模块名称（默认用仓库名）"),
            ("--path <路径>", "指定子模块路径（默认用仓库名）"),
            ("--branch <分支>", "指定追踪分支"),
        ],
        "examples": [
            ("gmm add https://github.com/user/repo.git", "添加单个仓库"),
            ("gmm add URL1 URL2 URL3", "批量添加"),
            ("gmm add <url> --name my-lib --path libs/my-lib", "自定义名称和路径"),
        ],
        "see_also": ["list", "run", "sync"],
    },

    "run": {
        "brief": "执行迁移",
        "usage": "gmm run [--dry-run]",
        "need_repo": True,
        "has_sub_help": False,
        "usage_formats": [
            ("gmm run", "在当前仓库目录下执行"),
            ("gmm <仓库名> run", "指定已注册仓库执行"),
        ],
        "desc": "遍历清单执行：克隆 -> Gitee建仓 -> 推送 -> 更新子模块引用。",
        "args": [],
        "opts": [
            ("--dry-run", "预览模式，只显示计划，不实际执行"),
        ],
        "examples": [
            ("gmm run --dry-run", "先预览"),
            ("gmm run", "确认后执行"),
        ],
        "prereq": [
            "已配置 Token: gmm config set gitee.token <token>",
            "清单不为空: gmm add <url> 或 gmm sync",
        ],
        "see_also": ["add", "list", "sync"],
    },

    "list": {
        "brief": "查看迁移清单和状态",
        "alias": "ls",
        "usage": "gmm list|ls",
        "need_repo": True,
        "has_sub_help": False,
        "usage_formats": [
            ("gmm list", "在当前仓库目录下执行"),
            ("gmm <仓库名> list", "指定已注册仓库执行"),
        ],
        "desc": "显示当前根仓库的迁移清单及处理状态。",
        "args": [],
        "opts": [],
        "examples": [
            ("gmm list", "查看清单"),
        ],
        "output_legend": [
            ("[ok]", "已迁移完成"),
            ("[  ]", "待处理"),
            ("[ok!]", "已完成但标记强制重迁"),
            ("->", "迁移后的新地址"),
        ],
        "see_also": ["add", "run"],
    },

    "sync": {
        "brief": "从现有子模块导入清单",
        "usage": "gmm sync",
        "need_repo": True,
        "has_sub_help": False,
        "usage_formats": [
            ("gmm sync", "在当前仓库目录下执行"),
            ("gmm <仓库名> sync", "指定已注册仓库执行"),
        ],
        "desc": "扫描 .gitmodules，将所有子模块 URL 自动加入迁移清单。",
        "args": [],
        "opts": [],
        "examples": [
            ("gmm sync", "导入所有子模块"),
            ("gmm sync && gmm list", "导入后查看"),
        ],
        "see_also": ["add", "list", "run"],
    },

    "mark": {
        "brief": "标记模块行为",
        "usage": "gmm mark <url> [选项]",
        "need_repo": True,
        "has_sub_help": False,
        "usage_formats": [
            ("gmm mark <url> [选项]", "在当前仓库目录下执行"),
            ("gmm <仓库名> mark <url> [选项]", "指定已注册仓库执行"),
        ],
        "desc": "为指定 URL 设置特殊处理标记。",
        "args": [
            ("<url>", "要标记的仓库 URL"),
        ],
        "opts": [
            ("--force-redo", "强制重新迁移（即使已完成）"),
            ("--skip-check", "跳过本地校验"),
        ],
        "examples": [
            ("gmm mark <url> --force-redo", "强制重迁某仓库"),
        ],
        "see_also": ["unmark", "list"],
    },

    "unmark": {
        "brief": "清除模块标记",
        "usage": "gmm unmark <url>",
        "need_repo": True,
        "has_sub_help": False,
        "usage_formats": [
            ("gmm unmark <url>", "在当前仓库目录下执行"),
            ("gmm <仓库名> unmark <url>", "指定已注册仓库执行"),
        ],
        "desc": "清除指定 URL 的所有标记。",
        "args": [
            ("<url>", "要清除标记的仓库 URL"),
        ],
        "opts": [],
        "examples": [
            ("gmm unmark <url>", "清除标记"),
        ],
        "see_also": ["mark"],
    },

    "clean": {
        "brief": "清空根仓库所有子模块",
        "usage": "gmm clean --force",
        "need_repo": True,
        "has_sub_help": False,
        "usage_formats": [
            ("gmm clean --force", "在当前仓库目录下执行"),
            ("gmm <仓库名> clean --force", "指定已注册仓库执行"),
        ],
        "desc": "删除所有子模块配置和目录。危险操作，必须加 --force。",
        "args": [],
        "opts": [
            ("--force", "确认执行删除（必需）"),
        ],
        "examples": [
            ("gmm clean --force", "清空所有子模块"),
        ],
        "see_also": [],
    },

    "config": {
        "brief": "全局配置管理",
        "alias": "cfg",
        "usage": "gmm config|cfg <set|get> <key> [value]",
        "need_repo": False,
        "has_sub_help": True,
        "usage_formats": [
            ("gmm config set <key> <value>", "设置配置项"),
            ("gmm config get <key>", "读取配置项"),
        ],
        "desc": "读取或设置全局配置。存储在 ~/.gmm/config.ini",
        "args": [
            ("set <key> <value>", "设置配置项"),
            ("get <key>", "读取配置项"),
        ],
        "opts": [],
        "examples": [
            ("gmm config set gitee.token <token>", "设置 Gitee Token"),
            ("gmm config get gitee.token", "查看 Token"),
            ("gmm config set 迁移.缓存目录 D:/cache", "设置缓存目录"),
        ],
        "config_keys": [
            ("gitee.token", "Gitee 访问令牌（必需）"),
            ("github.token", "GitHub 访问令牌（私有仓库需要）"),
            ("迁移.缓存目录", "克隆缓存目录，默认 ~/.gmm/cache/"),
            ("迁移.白名单域名", "不迁移的域名，默认 gitee.com, openi.pcl.ac.cn"),
        ],
        "see_also": [],
    },

    "repo": {
        "brief": "根仓库注册管理",
        "usage": "gmm repo <add|list|default|remove> [参数]",
        "need_repo": False,
        "has_sub_help": True,
        "usage_formats": [
            ("gmm repo add <名称> <路径>", "注册仓库"),
            ("gmm repo list", "列出所有注册"),
            ("gmm repo default <名称>", "设为默认"),
            ("gmm repo remove <名称>", "删除注册"),
        ],
        "desc": "注册后可在任意目录用 gmm <名称> <命令> 操作。不注册也可在仓库目录下直接执行。",
        "args": [
            ("add <名称> <路径>", "注册仓库"),
            ("list", "列出所有注册"),
            ("default <名称>", "设为默认"),
            ("remove <名称>", "删除注册"),
        ],
        "opts": [],
        "examples": [
            ("gmm repo add comfy D:/projects/ComfyUI", "注册仓库"),
            ("gmm repo list", "查看注册列表"),
            ("gmm comfy run", "在任意目录操作已注册仓库"),
        ],
        "see_also": [],
    },

}

# ═══════════════════════════════════════════════════════════
# 快速上手流程
# ═══════════════════════════════════════════════════════════
QUICKSTART = {
    "title": "快速上手",
    "steps": [
        ("gmm config set gitee.token <token>", "配置 Token（首次）"),
        ("gmm add <github仓库URL>", "添加要迁移的仓库"),
        ("gmm run", "执行迁移"),
    ],
}

# ═══════════════════════════════════════════════════════════
# 命令分组
# ═══════════════════════════════════════════════════════════
COMMAND_GROUPS = [
    {
        "name": "迁移操作",
        "desc": "在 Git 仓库目录下执行，或用 gmm <仓库名> <命令>",
        "commands": ["add", "sync", "list", "run", "mark", "unmark", "clean"],
    },
    {
        "name": "配置管理",
        "desc": "",
        "commands": ["config"],
    },
    {
        "name": "仓库注册",
        "desc": "可选，用于跨目录管理多个根仓库",
        "commands": ["repo"],
    },
]

# ═══════════════════════════════════════════════════════════
# 全局选项
# ═══════════════════════════════════════════════════════════
GLOBAL_OPTS = [
    ("--debug", "输出调试日志"),
    ("-h, --help", "显示帮助"),
    ("--help-full", "显示完整命令列表"),
]

# ═══════════════════════════════════════════════════════════
# 错误提示
# ═══════════════════════════════════════════════════════════
ERRORS = {
    "no_token": {
        "title": "未配置 Gitee Token",
        "hint": "请先获取 Token: https://gitee.com/personal_access_tokens",
        "action": "gmm config set gitee.token <你的token>",
    },
    "empty_list": {
        "title": "迁移清单为空",
        "hint": "请先添加要迁移的仓库",
        "action": "gmm add <url>  或  gmm sync",
    },
    "not_in_repo": {
        "title": "当前目录不是 Git 仓库",
        "hint": "请切换到 Git 仓库目录，或注册仓库后指定名称",
        "action": "cd <仓库目录>  或  gmm repo add <名称> <路径>",
    },
    "repo_not_found": {
        "title": "未找到指定的仓库",
        "hint": "请检查仓库名称是否正确",
        "action": "gmm repo list  查看已注册仓库",
    },
}


# ═══════════════════════════════════════════════════════════
# 格式化函数
# ═══════════════════════════════════════════════════════════

def format_brief_help() -> str:
    """生成简洁主帮助"""
    lines = [
        f"{META['name']} - {META['brief']}",
        "",
        f"[{QUICKSTART['title']}]",
    ]
    for i, (cmd, desc) in enumerate(QUICKSTART["steps"], 1):
        lines.append(f"  {i}. {cmd:<42}  # {desc}")

    lines.extend([
        "",
        "[命令一览]",
    ])
    for group in COMMAND_GROUPS:
        desc_part = f" ({group['desc']})" if group['desc'] else ""
        lines.append(f"  {group['name']}{desc_part}")
        for cmd_name in group["commands"]:
            cmd = COMMANDS[cmd_name]
            # 标注是否支持 <仓库名> 子帮助上下文
            标记 = ""
            if cmd['need_repo']:
                标记 = "  (需仓库)"
            别名 = cmd.get("alias", "")
            名称栏 = f"{cmd_name}|{别名}" if 别名 else cmd_name
            lines.append(f"    gmm {名称栏:<16} {cmd['brief']}{标记}")

    lines.extend([
        "",
        "[更多帮助]",
        "  gmm <命令> -h        查看命令的详细说明",
        "  gmm --help-full      查看所有命令完整列表",
        "",
        "提示：",
        "  - 标有 (需仓库) 的命令需要在 Git 仓库目录下执行，",
        "    或先用 gmm repo add <名称> <路径> 注册后使用 gmm <名称> <命令>",
        "  - gmm config 和 gmm repo 有自己的子命令，可用 -h 查看子帮助",
        "  - 支持一次添加多个 URL：gmm add <url1> <url2> <url3>",
    ])
    return "\n".join(lines)


def format_full_help() -> str:
    """生成完整帮助"""
    lines = [
        f"{META['name']} - {META['brief']}",
        "",
    ]
    
    for group in COMMAND_GROUPS:
        desc_part = f" ({group['desc']})" if group['desc'] else ""
        lines.append(f"[{group['name']}]{desc_part}")
        for cmd_name in group["commands"]:
            cmd = COMMANDS[cmd_name]
            别名 = cmd.get("alias", "")
            名称栏 = f"{cmd_name}|{别名}" if 别名 else cmd_name
            lines.append(f"  {名称栏:<16} {cmd['brief']}")
            # 显示两种用法格式
            for fmt, desc in cmd.get("usage_formats", []):
                lines.append(f"    ├─ {fmt}")
                lines.append(f"    └─ {desc}")
        lines.append("")
    
    lines.append("[全局选项]")
    for opt, desc in GLOBAL_OPTS:
        lines.append(f"  {opt:<18} {desc}")
    
    lines.extend([
        "",
        "注：",
        "  需要根仓库的命令支持两种执行方式：",
        "    1. 直接 cd 到仓库目录，执行 gmm <命令>",
        "    2. 先 gmm repo add <名称> <路径> 注册，再 gmm <名称> <命令>",
    ])

    return "\n".join(lines)


def format_command_help(cmd_name: str) -> str:
    """生成单个命令的详细帮助"""
    if cmd_name not in COMMANDS:
        return f"未知命令: {cmd_name}"
    
    cmd = COMMANDS[cmd_name]
    lines = [
        cmd["brief"],
        "",
        "[用法]",
        f"  {cmd['usage']}",
        "",
        "[说明]",
        f"  {cmd['desc']}",
    ]

    # 如果有别名，额外提示
    别名 = cmd.get("alias", "")
    if 别名:
        lines.append(f"")
        lines.append(f"[别名]  {别名}（等效于 {cmd_name}）")

    if cmd.get("args"):
        lines.extend(["", "[参数]"])
        for arg, desc in cmd["args"]:
            lines.append(f"  {arg:<20} {desc}")
    
    if cmd.get("opts"):
        lines.extend(["", "[选项]"])
        for opt, desc in cmd["opts"]:
            lines.append(f"  {opt:<20} {desc}")
    
    if cmd.get("prereq"):
        lines.extend(["", "[前置条件]"])
        for prereq in cmd["prereq"]:
            lines.append(f"  - {prereq}")
    
    if cmd.get("config_keys"):
        lines.extend(["", "[配置项]"])
        for key, desc in cmd["config_keys"]:
            lines.append(f"  {key:<20} {desc}")
    
    if cmd.get("output_legend"):
        lines.extend(["", "[输出说明]"])
        for symbol, desc in cmd["output_legend"]:
            lines.append(f"  {symbol:<8} {desc}")
    
    if cmd.get("examples"):
        lines.extend(["", "[示例]"])
        for example, desc in cmd["examples"]:
            lines.append(f"  {example}")
            if desc:
                lines.append(f"      # {desc}")
    
    if cmd.get("see_also"):
        lines.extend(["", f"[相关命令] {', '.join(cmd['see_also'])}"])
    
    return "\n".join(lines)


def format_error(error_key: str) -> str:
    """生成错误提示"""
    if error_key not in ERRORS:
        return f"x 未知错误: {error_key}"
    
    err = ERRORS[error_key]
    lines = [
        f"x {err['title']}",
        "",
        f"  {err['hint']}",
        f"  -> {err['action']}",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 便捷导出
# ═══════════════════════════════════════════════════════════

def get_brief() -> str:
    return format_brief_help()

def get_full() -> str:
    return format_full_help()

def get_cmd(name: str) -> str:
    return format_command_help(name)

def get_error(key: str) -> str:
    return format_error(key)


if __name__ == "__main__":
    print("=" * 60)
    print("[简洁帮助]")
    print("=" * 60)
    print(get_brief())
    print()
    print("=" * 60)
    print("[完整帮助]")
    print("=" * 60)
    print(get_full())
    print()
    print("=" * 60)
    print("[add 命令帮助]")
    print("=" * 60)
    print(get_cmd("add"))
    print()
    print("=" * 60)
    print("[错误提示]")
    print("=" * 60)
    print(get_error("no_token"))