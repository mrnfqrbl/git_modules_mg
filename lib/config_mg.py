import configparser
import os

class ConfigMg:
    def __init__(self, 配置文件路径=None, 默认配置文件字典=None):
        # 配置文件路径
        self.配置文件路径 = 配置文件路径
        # 默认配置字典
        self.默认配置文件字典 = 默认配置文件字典

        # 非空校验
        if self.配置文件路径 is None:
            raise ValueError("配置文件路径不能为空")
        if self.默认配置文件字典 is None:
            raise ValueError("默认配置文件字典不能为空")

        # 底层配置工具（私有化，外部不访问）
        self._config = configparser.ConfigParser()
        self.加载配置()

    def 加载配置(self):
        """加载配置：文件不存在则自动创建，存在则直接读取，并自动合并缺失的配置项"""
        if not os.path.exists(self.配置文件路径):
            # 用默认配置初始化文件
            for 节点 in self.默认配置文件字典:
                self._config.add_section(节点)
                for 键, 值 in self.默认配置文件字典[节点].items():
                    self._config.set(节点, 键, str(值))
            # 保存初始化的配置
            self._保存到文件()
        else:
            # 读取配置文件
            self._config.read(self.配置文件路径, encoding="utf-8")
            # 自动补全缺失的配置项
            修改过 = False
            for 节点, 键值对 in self.默认配置文件字典.items():
                if not self._config.has_section(节点):
                    self._config.add_section(节点)
                    修改过 = True
                for 键, 值 in 键值对.items():
                    if not self._config.has_option(节点, 键):
                        self._config.set(节点, 键, str(值))
                        修改过 = True
            if 修改过:
                self._保存到文件()

        # ✅ 返回管家自身，不返回底层工具
        return self

    def _保存到文件(self):
        """【私有方法】自动保存配置到文件（自动更新核心）"""
        with open(self.配置文件路径, "w", encoding="utf-8") as f:
            self._config.write(f)

    # ==================== 封装对外方法：通过管家操作 ====================
    def set(self, 节点, 键, 值):
        """
        设置配置值 → 修改后【自动保存到文件】
        :param 节点: 如 github/gitee
        :param 键: 如 token
        :param 值: 你要设置的内容
        """
        # 节点不存在自动创建
        if not self._config.has_section(节点):
            self._config.add_section(节点)
        # 设置值
        self._config.set(节点, 键, str(值))
        # ✅ 核心：自动保存，无需手动操作
        self._保存到文件()

    def get(self, 节点, 键):
        """获取配置值"""
        return self._config.get(节点, 键)