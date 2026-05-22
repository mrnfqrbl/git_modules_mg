"""
帮助信息集中管理
================
所有 --help 文本集中在此，main.py 只引用变量名。
"""

主帮助说明 = """\
Git 仓库批量迁移与子模块管理全局 CLI 工具

使用示例：
  gmm repo add myrepo D:/path/to/repo    注册根仓库
  gmm repo list                           查看已注册的根仓库
  gmm config set gitee.token <token>      配置 Gitee token
  gmm config get gitee.token              查看 Gitee token
  gmm myrepo sync                         扫描根仓库子模块加入清单
  gmm myrepo add <url>                    手动添加模块到清单
  gmm myrepo list                         查看清单与缓存状态
  gmm myrepo run --dry-run                试运行迁移
  gmm myrepo run                          执行迁移
  gmm myrepo mark <url> --force-redo      标记强制重迁
  gmm myrepo clean --force                清空根仓库所有子模块
"""

repo帮助 = """\
示例：
  gmm repo add myrepo D:/path/to/repo    注册
  gmm repo remove myrepo                 删除
  gmm repo list                          查看
  gmm repo default myrepo                设为默认
"""

config帮助 = """\
示例：
  gmm config set gitee.token abc123      设置 Gitee token
  gmm config get gitee.token             读取 Gitee token
  gmm config set 迁移.缓存目录 ~/.gmm/cache  设置缓存目录
"""
